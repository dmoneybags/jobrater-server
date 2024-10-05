#(c) 2024 Daniel DeMoney. All rights reserved.
'''
Execution flow:

Background.js

Listens for: a tab change event fired when the current tabs url changes
Executes: scrapes the jobId from the url
Sends: a message to the contentScript that we recieved a new job

ContentScript.js
Listens for: the new job event from background.js
Executes the scraping of the linkedin and glassdoor
Calls:

database_server.py
Listens for: requests sent on PORT 5001
Executes the database functions to CRUD jobs

TO DO:

load function, can be called when a user loads the app to grab all their data if not
initialized
'''
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(threadName)s]: %(message)s',
)

from flask import Flask, abort, request, Response, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from google.oauth2 import id_token
import uuid
from uuid import UUID
from dotenv import load_dotenv
from auth_logic import get_token
import jwt
import json
from mysql.connector.errors import IntegrityError
from auth_logic import decode_user_from_token, token_required
from job_location_table import JobLocationTable
from user_job_table import UserJobTable
from user_preferences import UserPreferences
from user_table import UserTable
from job_table import JobTable
from company_table import CompanyTable
from resume_table import ResumeTable
from user_location_table import UserLocationTable
from user_preferences_table import UserPreferencesTable
from user import UserInvalidData
from resume_nlp.resume_comparison import ResumeComparison
from resume_comparison_collection import ResumeComparisonCollection
from location_finder import LocationFinder
from relocation_data_grabber import RelocationDataGrabber
from company import Company
from job import Job
from user import User
from resume import Resume
from location import Location
from typing import Dict
import glassdoor_scraper
from helper_functions import HelperFunctions
import sys
import os
import traceback
import asyncio
import time
import requests
from urllib.parse import quote
from functools import partial
from errors import DuplicateUserJob
from gunicorn.app.base import BaseApplication

load_dotenv() 

#Set up our server using flask
app = Flask(__name__)
#Give support for cross origin requests from our content Script
CORS(app)
bcrypt = Bcrypt(app)
IS_PRODUCTION = os.getenv("ENVIRONMENT") == "production"
HOST="0.0.0.0" if IS_PRODUCTION else "127.0.0.1"
PORT=int(os.environ.get("PORT", 5001))

CANSCRAPEGLASSDOOR: bool = True
MAPBOXKEY: str = os.environ["MAPBOX_KEY"]
API_KEY : str = os.environ["GOOGLE_API_KEY"]

#All frequently queried routes are timed. If a route isnt timed its not used extremely often

class DatabaseServer:
    #########################################################################################
    #
    #
    # AUTH METHODS
    #
    '''
    auth_google

    recieves a request to authorize a user using the google token returned from authing with google

    args:
        Request
            google_token: token returned from authing with google
    returns:
        response with our auth token
    '''
    @app.route('/auth/google', methods=['POST'])
    def auth_google():
        google_token : str = request.args.get('google_token', default="NO TOKEN LOADED", type=str)
        try:
            # Verify the token using Google's API
            idinfo : Dict = id_token.verify_oauth2_token(google_token, requests.Request())

            email : str = idinfo['email']

            # Create a JWT token for the user
            jwt_token : str = jwt.encode({'email': email}, API_KEY, algorithm='HS256')
            return jsonify({'token': jwt_token})
        except ValueError:
            # Invalid token
            return 'Invalid token', 401

    '''
    get_salt_by_email

    grabs a users salt for hashing the password client side so we dont send plain text password over network

    args:
        request
            email: email of user to get salt for
    returns:
        salt
    '''
    @app.route('/get_salt_by_email', methods=["GET"])
    def get_salt_by_email():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO GET SALT BY EMAIL ================")
        logging.info(request.url)
        try:
            email : str = request.args.get('email', default="NO EMAIL LOADED", type=str)
            logging.debug("Got email from request")
        except:
            logging.error("Request of: " + request + " is invalid")
            #Invalid request
            return abort(403)
        user : User | None = UserTable.read_user_by_email(email)
        if not user:
            abort(404)
        logging.info(f"============== END REQUEST TO GET SALT BY EMAIL TOOK {time.time() - st} seconds ================")
        return jsonify({'salt': user.salt})
    '''
    login

    endpoint for a user logging in, checks that user is in db and compares password hashes

    args:
        request
            email: str email
            password_hash: password hashed with salt client side
    returns:
        response of either an error or user info
    '''
    @app.route('/login', methods=['POST'])
    def login():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO LOGIN ================")
        logging.info(request.url)
        email : str = request.args.get('email', default="NO EMAIL LOADED", type=str)
        password_hash : str = request.args.get('password', default="NO PASSWORD LOADED", type=str)

        user : User | None = UserTable.read_user_by_email(email)
        if not user:
            return 'User not found', 401
        logging.info("ATTEMPTING TO LOGIN USER: " + json.dumps(user.to_json()))
        #PASSWORDS ARE SALTED AND HASHED! do not be scared...
        logging.debug("HASH SENT BY CLIENT: " + password_hash)
        logging.debug("HASH FOUND IN DB: " + user.password)
        if not user.password == password_hash:
            logging.info("Passwords don't match")
            return 'Invalid email or password!', 401
        
        token, expiration_date = get_token(user)

        response : Response = jsonify({'token': token, 'user': user.to_json(), 'expirationDate': expiration_date})
        logging.info("LOGGED IN USER RETURNING RESPONSE: ")
        logging.info(response)
        logging.info(f"============== END REQUEST TO LOGIN TOOK {time.time() - st} seconds ================")
        return response
    '''
    register

    endpoint for a user registering in, checks that user is NOT db and registers

    args:
        request
            user_str: json dumped to str of user
            salt: salt for the hash
    returns:
        either http error 
    '''
    #NOTE: NEEDS TO BE ACID!!!
    @app.route('/register', methods=['POST'])
    def register():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO REGISTER ================")
        logging.info(request.url)
        try:
            body = request.json
            user_json : Dict = body["user"]
            logging.info("Registering user of:")
            logging.info(json.dumps(user_json, indent=2))
            salt: Dict = body["salt"]
        except KeyError as e:
            logging.error("User passed with invalid data, keyError trying to key")
            return "Bad User Data", 400
        try:
            logging.info("Loading user into Object...")
            user : User = User.create_with_json(user_json)
        except UserInvalidData:
            logging.error("User passed with invalid data")
            return "Bad User Data", 400
        if not user.password:
            logging.error("User passed without password")
            return "Bad User Data", 400
        user.salt = salt
        logging.debug("Checking if user exists...")
        if UserTable.read_user_by_email(user.email):
            logging.info("User already exists, returning a 401")
            return 'User already exists!', 401
        
        user_id : UUID = str(uuid.uuid1())
        user.user_id = user_id
        if user.preferences:
            user.preferences.user_id = user_id
        logging.info("USER VALIDATED TO REGISTER")

        UserTable.add_user(user)
        
        #for debug, we will error in production if no preference
        if user.preferences:
            logging.info("ADDING PREFERENCES TO DB")
            UserPreferencesTable.add_user_preferences(user.preferences)
            logging.info("ADDED PREFERENCES TO DB")
        else:
            logging.info("NO PREFERENCES FOUND, ONLY NOT ERRORING FOR TESTING PURPOSES")
        if user.location:
            logging.info("ADDING LOCATION TO DB")
            UserLocationTable.add_user_location(user.location, user.user_id)
        else:
            logging.info("USER IS CHOOSING NOT TO ADD LOCATION")

        token, expiration_date = get_token(user)

        logging.info("Setting userId to " + user_id)
        logging.info("Setting token to " + token)

        logging.info(f"============== END REQUEST TO REGISTER TOOK {time.time() - st} seconds ================")
        return jsonify({'token': token, 'userId': user_id, 'expirationDate': expiration_date})
    #########################################################################################

    #
    #
    # JOB METHODS
    #
    #
    '''
    add_job

    recieves the request to add a job and executes the request
        request
            token: str token of the users auth
    
    returns Response
    '''
    @app.route('/databases/add_job', methods=['POST'])
    @token_required
    def add_job():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO ADD JOB ================")
        logging.info(request.url)
        async def get_company_data_async(company: str) -> Dict:
            return await glassdoor_scraper.get_company_data(company)

        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        if not user:
            return "NO TOKEN SENT", 401
        user_id : str = user.user_id
        try:
            message : Dict = request.json
            logging.info(f"Message keys: {list(message.keys())}")
            job_json : Dict = message["job"]
            logging.debug("=============== RECIEVED JOB JSON OF =========== \n\n")
            logging.debug(json.dumps(job_json, indent=4))
            company_name: str = job_json["company"]["companyName"]
            logging.info("CHECKING IF WE NEED TO SCRAPE GLASSDOOR")
            if (not CompanyTable.read_company_by_id(company_name) and CANSCRAPEGLASSDOOR and not message["noCompanies"]):
                if (not message["gdPageSource"]):
                    t1 = time.time()
                    logging.info("RETRIEVING COMPANY FROM GLASSDOOR")
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    company_data: Dict = loop.run_until_complete(get_company_data_async(company_name))
                    company : Company = Company(company_name, company_data["businessOutlookRating"], 
                                                company_data["careerOpportunitiesRating"], company_data["ceoRating"],
                                                company_data["compensationAndBenefitsRating"],
                                                company_data["cultureAndValuesRating"],
                                                company_data["diversityAndInclusionRating"],
                                                company_data["seniorManagementRating"],
                                                company_data["workLifeBalanceRating"],
                                                company_data["overallRating"],
                                                company_data["glassdoorUrl"])
                    job_json["company"] = company.to_json()
                    t2 = time.time()
                    logging.info("Scraping glassdoor took: " + str(t2 - t1) + " seconds")
                else:
                    logging.info("CLIENT SENT SOURCE")
                    company_data = glassdoor_scraper.get_company_from_page_source(message["gdPageSource"], message["gdUrl"])
                    company : Company = Company(company_name, company_data["businessOutlookRating"], 
                                                company_data["careerOpportunitiesRating"], company_data["ceoRating"],
                                                company_data["compensationAndBenefitsRating"],
                                                company_data["cultureAndValuesRating"],
                                                company_data["diversityAndInclusionRating"],
                                                company_data["seniorManagementRating"],
                                                company_data["workLifeBalanceRating"],
                                                company_data["overallRating"],
                                                company_data["glassdoorUrl"])
                    job_json["company"] = company.to_json()
            else:
                logging.info("NO NEED TO SCRAPE GLASSDOOR")
            print("\n\n")
        except json.JSONDecodeError:
            logging.error("YOUR JOB JSON OF " + message + "IS INVALID")
            #Invalid request
            abort(403)
        logging.debug(job_json)
        job : Job = Job.create_with_json(job_json)
        logging.info("RECIEVED MESSAGE TO ADD JOB WITH ID " + job_json["jobId"])
        #Call the database function to execute the insert
        #we complete the jobs data before returning it to the client
        #NOTE: Needs to be acid
        try:
            completeJob: Job = JobTable.add_job_with_foreign_keys(job, user_id)
        except DuplicateUserJob:
            abort(409) 
        assert(completeJob.company is not None)
        logging.info(f"============== END REQUEST TO ADD JOB TOOK {time.time() - st} seconds ================")
        return json.dumps({"job": completeJob.to_json()}), 200
    '''
    read_most_recent_job

    reads the most recently added job from the db

    args:
        None
    returns:
        json representation of job
    '''
    @app.route('/databases/read_most_recent_job', methods=['GET'])
    @token_required
    def read_most_recent_job():
        logging.info("=============== BEGIN READ MOST RECENT JOB =================")
        logging.info(request.url)
        #Call the database function to select and sort to the most recent job
        job : Job | None = JobTable.read_most_recent_job()
        if not job:
            #Not found
            logging.critical("DB IS EMPTY")
            abort(404)
        logging.debug("RETURNING RESULT")
        logging.info("=============== END READ MOST RECENT JOB =================")
        return job.to_json()
    '''
    read_job_by_id

    recieves request to read a company by the companies str id and returns the json representation of the job 

    args:
        request
            job_id str job id from linkedin
    returns:
        json representation of job
    '''
    @app.route('/databases/read_job_by_id', methods=['GET'])
    @token_required
    def read_job_by_id():
        logging.info("=============== BEGIN READ JOB BY ID =================")
        logging.info(request.url)
        #Grab the jobId from the request, it is in the form of a string
        try:
            job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        except:
            #invalid request
            logging.info("Your request of: " + request)
            abort(403)
        logging.info("JOB ID:  " + job_id)
        job : Job | None = JobTable.read_job_by_id(job_id)
        if not job:
            logging.error("JOB NOT IN DB")
            abort(404)
        logging.info("=============== END READ JOB BY ID =================")
        return job.to_json()
    '''
    update_job

    recieves request to update company

    args:
        request
            jobJson the json of the job to set the job to
    returns:
        response message and code
    '''
    @app.route('/databases/update_job', methods=['POST'])
    @token_required
    def update_job():
        logging.info("=============== BEGIN UPDATE JOB BY ID =================")
        logging.info(request.url)
        #We take an argument of the whole job data in the from a json string
        try:
            message : str = request.args.get('jobJson', default="NO JOB JSON LOADED", type=str)
            job_json : Dict = json.loads(message)
            job : Job = Job.create_with_json(job_json)
        except json.JSONDecodeError:
            logging.error("YOUR JOB JSON OF " + request + "IS INVALID")
            #Invalid request
            abort(403)
        JobTable.update_job(job)
        logging.info("=============== END UPDATE JOB BY ID =================")
        return 'success', 200
    '''
    delete_job

    recieves request to delete company

    args:
        request
            job_id the id of the job to delete
    returns:
        response message and code
    '''
    @app.route('/databases/delete_job', methods=['POST'])
    @token_required
    def delete_job():
        logging.info("=============== BEGIN DELETE JOB BY ID =================")
        logging.info(request.url)
        #Get the job id from the request
        try:
            job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        except:
            logging.error("Request of: " + request + " is invalid")
            #Invalid request
            abort(403)
        #run the sql code
        JobTable.delete_job_by_id(job_id)
        logging.info("=============== END DELETE JOB BY ID =================")
        return 'success', 200
    #
    #
    # COMPANY METHODS
    #
    #
    #We only give the server an option to read companies,
    #theres no reason for us to make calls to update or delete companies yet
    '''
    read_company_by_name

    responds to request and gets a companys data by name

    args:
        request
            company: str company name
    returns
        company json
    '''
    #Unused as of now
    @app.route('/databases/read_company', methods=["GET"])
    @token_required
    def read_company_by_name():
        try:
            company : str = request.args.get('company', default="NO COMPANY LOADED", type=str)
        except:
            logging.error("Request of: " + request + " is invalid")
            #Invalid request
            abort(403)
        logging.info("Recieved message to read company: " + company)
        company : Company | None = CompanyTable.read_company_by_id(company)
        if not company:
            abort(404)
        return company.to_json()
    #
    #
    # USER METHODS
    #
    #
    '''
    get_user_data

    responds to a request to retrive the users data from the dbs

    for now just:
        user columns
        user jobs
    
    args:
        request
            token: JWT token that holds user id
    returns:
        json with user data and job data
    '''
    @app.route('/databases/get_user_data', methods=["GET"])
    @token_required
    def get_user_data():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO GET USER JOB ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            abort(404)
        jobs : list[Job] = UserJobTable.get_user_jobs(user.user_id)
        #TODO: clear file text and bytes no need to send it over the net
        resumes: list[Resume] = ResumeTable.read_user_resumes(user.user_id)
        json_jobs : list[Dict] = [job.to_json() for job in jobs]
        json_resumes : list[Dict] = [resume.to_json() for resume in resumes]
        best_resume_scores : Dict = ResumeComparisonCollection.get_best_resume_scores_object(jobs, user.user_id)
        return_json = {"user": user.to_json(), "jobs": json_jobs, "resumes": json_resumes, "bestResumeScores": best_resume_scores}
        logging.info(f"=============== END GET USER JOB TOOK {time.time() - st} seconds =================")
        return json.dumps(return_json)
    @app.route('/databases/update_user_job', methods=["POST"])
    def update_user_job():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO UPDATE USER JOB ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            logging.error("Couldn't find user")
            abort(404)
        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        if (job_id == "NO JOB ID LOADED"):
            logging.info("Couldn't find job")
            abort(400)
        update_json = request.get_json()["updateDict"]
        logging.info(f"============== END REQUEST TO UPDATE USER JOB TOOK {time.time() - st} seconds ================")
        return json.dumps(UserJobTable.update_user_job(job_id, user.user_id, update_json).to_json())  
    @app.route('/databases/delete_user_job', methods=["POST"])
    @token_required
    def delete_user_job():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO DELETE USER JOB ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            logging.error("Couldn't find user")
            abort(404)
        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        if (job_id == "NO JOB ID LOADED"):
            logging.error("Couldn't find job")
            abort(400)
        UserJobTable.delete_user_job(user.user_id, job_id)
        logging.info(f"=============== END DELETE USER JOB TOOK {time.time() - st} seconds=================")
        return 'success', 200
    '''
    delete_user

    deletes a user using the token passed in the request

    args:
        request
            token: jwt auth token
    returns:
        success message or error
    '''
    @app.route('/databases/delete_user', methods=['POST'])
    @token_required
    def delete_user():
        logging.info("=============== BEGIN DELETE USER =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        user_email : str = user.email
        if not UserTable.read_user_by_email(user_email):
            return json.dumps({'message': 'User not in db'}), 401
        UserTable.delete_user_by_email(user_email)
        logging.info("=============== END DELETE USER =================")
        return 'success', 200
    '''
    update_user_preferences

    updates a users preferences when passed a json dictionary of key to new value

    args:
        request
            body["updateJson"]
    returns:
        the new full preferences object
    '''
    @app.route('/databases/update_user_preferences', methods=['POST'])
    @token_required
    def update_user_preferences():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO UPDATE USER PREFERENCES ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        updateJson: Dict = request.get_json()["updateJson"]
        newPreferences: UserPreferences = UserPreferencesTable.update_user_preferences(updateJson, user.user_id)
        logging.info(f"============== END REQUEST TO UPDATE USER PREFERENCES {time.time() - st} seconds================")
        return json.dumps(newPreferences.to_json())
    '''
    update_user_location

    updates a users location when passed a json dictionary of key to new value

    args:
        request
            body["updateJson"]
    returns:
        the new full location object
    '''
    @app.route('/databases/update_user_location', methods=['POST'])
    @token_required
    def update_user_location():
        logging.info("=============== BEGIN UPDATE USER LOCATION =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        updateJson: Dict = request.get_json()["updateJson"]
        #the user could not have a location yet, if they dont our update wont work, we have to add
        if (UserLocationTable.try_read_location(user.user_id)):
            newLocation: Location = UserLocationTable.update_location(user.user_id, updateJson)
            logging.info("=============== END UPDATE USER LOCATION =================")
            return json.dumps(newLocation.to_json())
        else:
            location: Location = Location.try_get_location_from_json(updateJson)
            UserLocationTable.add_user_location(location, user.user_id)
            logging.info("=============== END UPDATE USER LOCATION =================")
            return json.dumps(location.to_json())
    '''
    delete_user_location

    deletes a users location

    returns:
        "success" if we found a location and deleted it
    '''
    @app.route('/databases/delete_user_location', methods=['POST'])
    @token_required
    def delete_user_location():
        logging.info("=============== BEGIN DELETE USER LOCATION =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        UserLocationTable.delete_location(user.user_id)
        logging.info("=============== END DELETE USER LOCATION =================")
        return "success", 200
    #
    # RESUME METHODS
    #
    #
    '''
    add_resume

    Adds a resume to our db

    also gets additional data on resume (for pdfs file text and such)

    req:
        resume: resume Json
    returns:
        dumped resume we added
    '''
    @app.route('/databases/add_resume', methods=['POST'])
    @token_required
    def add_resume():
        st = time.time()
        logging.info("============== GOT REQUEST TO ADD RESUME ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        request_json: Dict = request.get_json()
        resume_json: Dict = request_json["resume"]
        #Check for the key first to make sure theres no keyError and then check to make sure its true
        if "replace" in request_json and request_json["replace"]:
            logging.info("REPLACING RESUME")
            ResumeTable.delete_resume(request_json["oldId"])
        resume: Resume = Resume.create_with_json(resume_json)
        resume.user_id = str(user.user_id)
        resume_json: Dict = ResumeTable.add_resume(user.user_id, resume)
        logging.info(f"=============== END ADD RESUME TOOK {time.time() - st} =================")
        return json.dumps(resume_json)
    '''
    delete_resume

    deletes a resume from our db by id

    TODO: Should put in a check that this is actually the users resume

    request
        resumeId: id of resume
    returns:    
        nothing of note
    '''
    @app.route('/databases/delete_resume', methods=['POST'])
    @token_required
    def delete_resume():
        logging.info("=============== BEGIN DELETE RESUME =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        resume_id: str = request.args.get('resumeId', default="NO RESUME LOADED", type=str)
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        ResumeTable.delete_resume(resume_id)
        logging.info("=============== END DELETE RESUME =================")
        return 'success', 200
    @app.route('/databases/read_resume', methods=['GET'])
    @token_required
    def read_resume():
        logging.info("=============== BEGIN READ RESUME =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        resume_id: str = request.args.get('resumeId', default="NO RESUME LOADED", type=str)
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if resume:
            return json.dumps(resume.to_json())
        logging.info("=============== END READ RESUME =================")
        return "Could not find resume with id", 404
    @app.route('/databases/update_resume', methods=['POST'])
    @token_required
    def update_resume():
        logging.info("=============== BEGIN UPDATE RESUME =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        resume_id: str = request.args.get('resumeId', default="NO RESUME LOADED", type=str)
        update_json: str = request.get_json()
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        #wrap in try catch
        logging.info("=============== END UPDATE RESUME =================")
        return json.dumps(ResumeTable.update_resume_by_id(resume_id, user.user_id, update_json).to_json())
    '''
    compare_resumes

    compares all users resumes in the db against a job description
    '''
    @app.route('/databases/compare_resumes', methods=['POST'])
    @token_required
    def compare_resumes():
        logging.info("=============== BEGIN COMPARE RESUMES =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        req_json = request.get_json()
        job_description: str = req_json["jobDescription"]
        job_id = req_json["jobId"]
        resumes: list[Resume] = ResumeTable.read_user_resumes(user.user_id)
        resume_comparison_data: Dict = {}
        for resume in resumes:
            resume_comparison_data[resume.id] = ResumeComparison.get_resume_comparison_dict(job_description, job_id, resume, user.user_id)
        ResumeComparisonCollection.add_resume_comparisons(list(resume_comparison_data.values()))
        logging.info("=============== END COMPARE RESUMES =================")
        return json.dumps(resume_comparison_data) 
    '''
    compare_resumes_by_id

    User sends id of resume to compare, we read it from the db, and then compare it
    '''
    @app.route('/databases/compare_resumes_by_id', methods=['POST'])
    @token_required
    def compare_resumes_by_id():
        logging.info("=============== BEGIN COMPARE RESUMES BY ID =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        req_json = request.get_json()
        job_description: str = req_json["jobDescription"]
        job_id = req_json["jobId"]
        resume_id = req_json["resumeId"]
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        resume_comparison_data = ResumeComparison.get_resume_comparison_dict(job_description, job_id, resume, user.user_id)
        ResumeComparisonCollection.add_resume_comparison(resume_comparison_data)
        logging.info("=============== END COMPARE RESUMES BY ID =================")
        return json.dumps(resume_comparison_data) 
    '''
    get_specific_resume_comparison

    Takes args of resume_id, job_id and returns resume comparison if found.

    404s if not found

    should check if user is paying
    '''
    @app.route('/databases/get_specific_resume_comparison', methods=["GET"])
    @token_required
    def get_specific_resume_comparison():
        st = time.time()
        logging.info("============== GOT REQUEST TO GET SPECIFIC RESUME COMPARISON ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)

        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        resume_id : str = request.args.get('resumeId', default="NO RESUME ID LOADED", type=str)
        logging.info({"job_id": job_id})
        logging.info({"resume_id": resume_id})
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            logging.error("Resume not found")
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            logging.error("Invalid Id")
            return 'Invalid Id', 403
        resume_comparison = ResumeComparisonCollection.read_specific_resume_comparison(job_id, resume_id)
        if not resume_comparison:
            logging.error("Could not find resume comparison with ids")
            return "Could not find resume comparison with ids", 404
        #Remove mongodb id
        del resume_comparison["_id"]
        logging.info(f"=============== END GET SPECIFIC RESUME COMPARISON TOOK {time.time() - st} seconds=================")
        return json.dumps(resume_comparison)
    '''
    FOR TESTING ONLY

    compare_resume_from_request

    almost entirely built for the debug menu

    a resume is sent in the req.body and we compare on the backend and send back the info
    '''
    @app.route('/databases/compare_resumes_from_request', methods=['POST'])
    @token_required
    def compare_resume_from_request():
        logging.info("=============== BEGIN COMPARE RESUME FROM REQUEST =================")
        logging.info(request.url)
        #is this double the db work because we're getting the user twice?
        #once from token required, once from this
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        req_json = request.get_json()
        job_id = req_json["jobId"]
        job_description: str = req_json["jobDescription"]
        logging.debug("Loaded job description")
        resume_json: Dict = request.get_json()["resume"]
        resume: Resume = Resume.create_with_json(resume_json)
        logging.debug("got resumes")
        resume_comparison_data = ResumeComparison.get_resume_comparison_dict(job_description, job_id, resume, user.user_id)
        #Not going to add these to db, pretty much just for debugview
        logging.debug("Returning data")
        logging.info("=============== END COMPARE RESUME FROM REQUEST =================")
        return json.dumps(resume_comparison_data) 
    
    @app.route('/databases/compare_resume_by_ids', methods=['GET'])
    @token_required
    def compare_resume_by_ids():
        st = time.time()
        logging.info("=============== GOT REQUEST TO COMPARE RESUME BY IDS =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        resume_id : str = request.args.get('resumeId', default="NO RESUME ID LOADED", type=str)
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            logging.error(f"Could not find resume with id: {resume_id}")
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        job : Job = JobTable.read_job_by_id(job_id)
        if not job:
            logging.error(f"Could not find job with id: {job_id}")
            return "Job not found", 404
        resume_comparison_data = ResumeComparison.get_resume_comparison_dict(job.description, job_id, reread_resume, user.user_id)
        ResumeComparisonCollection.add_resume_comparison(resume_comparison_data)
        #Remove mongodb id
        del resume_comparison_data["_id"]
        logging.info(f"=============== END COMPARE RESUME BY IDS TOOK {time.time() - st} seconds =================")
        return json.dumps(resume_comparison_data)
    @app.route('/api/verify_address', methods=['GET'])
    def verify_address():
        logging.info("=============== BEGIN VERIFY ADDRESS =================")
        logging.info(request.url)
        search_json: Dict = json.loads(request.args.get("searchJson"))
        if not search_json:
            return "No address sent", 400
        search_text: str = search_json["street"] + " " + search_json["city"] + " " + search_json["zipCode"] + " " + search_json["stateCode"]
        endpoint: str = "mapbox.places"
        #quoting to uri encode it
        mapbox_response: Dict = requests.get(f"https://api.mapbox.com/geocoding/v5/{endpoint}/{quote(search_text)}.json?access_token={MAPBOXKEY}").json()
        main_location: Dict = mapbox_response["features"][0]
        logging.info("Verified location to:")
        logging.info(main_location)
        try:
            logging.info("=============== END VERIFY ADDRESS =================")
            return json.dumps({"coordinates": main_location["geometry"]["coordinates"]})
        except KeyError:
            logging.error("=============== END VERIFY ADDRESS =================")
            logging.error("ERROR VERIFYING, GOT KEYERROR TRYING TO CREATE RETURN JSON")
            return "invalid location", 400
    @app.route('/api/directions', methods=['GET'])
    @token_required
    def get_directions():
        logging.info("=============== BEGIN GET DIRECTIONS =================")
        logging.info(request.url)
        origin_lat = request.args.get('originLat')
        origin_lng = request.args.get('originLng')
        dest_lat = request.args.get('destLat')
        dest_lng = request.args.get('destLng')
        if not origin_lat or not origin_lng or not dest_lat or not dest_lng:
            logging.error("MISSING PARAMETERS! Cannot get directions")
            return json.dumps({'message': 'Missing required parameters'}), 400
        responseJson = LocationFinder.get_directions(origin_lat, origin_lng, dest_lat, dest_lng)
        if not responseJson:
            return json.dumps({'message': 'Failed to grab location'}), 400
        responseJsonReversed = LocationFinder.get_directions(dest_lat, dest_lng, origin_lat, origin_lng, returning=True)
        responseJson["leavingDuration"] = responseJsonReversed["arrivingDuration"]
        responseJson["leavingTrafficDuration"] = responseJsonReversed["arrivingTrafficDuration"]
        logging.info("=============== END GET DIRECTIONS =================")
        return json.dumps(responseJson), 200
    @app.route('/api/get_relocation_data', methods=['POST'])
    @token_required
    def get_relocation_data():
        st = time.time()
        logging.info("=============== BEGIN GET RELOCATION DATA =================")
        logging.info(request.url)
        req_json = request.get_json()
        location_json = req_json["location"]
        location = Location.try_get_location_from_json(location_json)
        logging.debug("LOADED LOCATION!")
        logging.debug(json.dumps(location_json, indent=2))
        if not location:
            logging.error("Failed to get location from request body")
            return json.dumps({'message': 'Missing required parameters'}), 400
        relocation_data = asyncio.run(RelocationDataGrabber.get_data(location))
        logging.info(f"=============== END GET RELOCATION DATA TOOK {time.time() - st} seconds =================")
        return json.dumps(relocation_data), 200
    @app.route('/api/verify_token', methods=['GET'])
    def verify_token():
        logging.debug("=============== BEGIN VERIFY TOKEN =================")
        token : str = request.headers.get('Authorization')
        logging.debug(token)
        try:
            user : User | None = decode_user_from_token(token)
            logging.debug("=============== END VERIFY TOKEN =================")
            if user:
                return "AUTHED", 200
            else:
                return "NO_AUTH", 200
        except:
            return "NO_AUTH", 200
    def shutdown():
        logging.critical("Handling database server shutdown")
        HelperFunctions.handle_sigterm("database_server")
        logging.info("Shutdown successful")
    def run():
        logging.info("Running server")
        try:
            app.run(debug=False, host=HOST, port=PORT, ssl_context=(os.path.join(os.getcwd(), "cert.pem"), os.path.join(os.getcwd(), "key.pem")))
        except:
            DatabaseServer.shutdown()

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)            
if __name__ == '__main__':
    HelperFunctions.write_pid_to_temp_file("database_server")
    DatabaseServer.run()
    '''
    try:
        # Check for the -I argument
        if '-i' in sys.argv:
            # Run the script normally without daemonizing
            print("Running in non-daemon mode")
            app.run(debug=False, port=PORT)
        else:
            DatabaseServer.run_as_daemon()
    except Exception as e: 
        raise e
    finally:
        DatabaseServer.shutdown()
    '''
