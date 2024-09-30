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
        print("Recieved Message to get salt by email")
        try:
            email : str = request.args.get('email', default="NO EMAIL LOADED", type=str)
            print("Got email from request")
        except:
            print("Request of: " + request + " is invalid")
            #Invalid request
            return abort(403)
        user : User | None = UserTable.read_user_by_email(email)
        if not user:
            abort(404)
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
        email : str = request.args.get('email', default="NO EMAIL LOADED", type=str)
        password_hash : str = request.args.get('password', default="NO PASSWORD LOADED", type=str)

        user : User | None = UserTable.read_user_by_email(email)
        if not user:
            return 'User not found', 401
        print("ATTEMPTING TO LOGIN USER: " + json.dumps(user.to_json()))
        #PASSWORDS ARE SALTED AND HASHED! do not be scared...
        print("HASH SENT BY CLIENT: " + password_hash)
        print("HASH FOUND IN DB: " + user.password)
        if not user.password == password_hash:
            print("Passwords don't match")
            return 'Invalid email or password!', 401
        
        token, expiration_date = get_token(user)

        response : Response = jsonify({'token': token, 'user': user.to_json(), 'expirationDate': expiration_date})
        print("LOGGED IN USER RETURNING RESPONSE: ")
        print(response)
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
        print("GOT REQUEST TO REGISTER USER")
        try:
            body = request.json
            user_json : Dict = body["user"]
            print("Registering user of:")
            print(json.dumps(user_json, indent=2))
            salt: Dict = body["salt"]
        except KeyError as e:
            return "Bad User Data", 400
        try:
            print("Loading user into Object...")
            user : User = User.create_with_json(user_json)
        except UserInvalidData:
            return "Bad User Data", 400
        if not user.password:
            return "Bad User Data", 400
        user.salt = salt
        print("Checking if user exists...")
        if UserTable.read_user_by_email(user.email):
            return 'User already exists!', 401
        
        user_id : UUID = str(uuid.uuid1())
        user.user_id = user_id
        if user.preferences:
            user.preferences.user_id = user_id
        print("USER VALIDATED TO REGISTER")

        UserTable.add_user(user)
        
        #for debug, we will error in production if no preference
        if user.preferences:
            print("ADDING PREFERENCES TO DB")
            UserPreferencesTable.add_user_preferences(user.preferences)
            print("ADDED PREFERENCES TO DB")
        else:
            print("NO PREFERENCES FOUND, ONLY NOT ERRORING FOR TESTING PURPOSES")
        if user.location:
            print("ADDING LOCATION TO DB")
            UserLocationTable.add_user_location(user.location, user.user_id)
        else:
            print("USER IS CHOOSING NOT TO ADD LOCATION")

        token, expiration_date = get_token(user)

        print("Setting userId to " + user_id)
        print("Setting token to " + token)

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
        print("=============== BEGIN ADD JOB =================")
        async def get_company_data_async(company: str) -> Dict:
            return await glassdoor_scraper.get_company_data(company)

        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        if not user:
            return "NO TOKEN SENT", 401
        user_id : str = user.user_id
        try:
            message : str = request.json
            job_json : Dict = message["job"]
            print("=============== RECIEVED JOB JSON OF =========== \n\n")
            print(json.dumps(job_json, indent=4))
            company_name: str = job_json["company"]["companyName"]
            if (not CompanyTable.read_company_by_id(company_name) and CANSCRAPEGLASSDOOR):
                t1 = time.time()
                print("RETRIEVING COMPANY FROM GLASSDOOR")
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
                print("Scraping glassdoor took: " + str(t2 - t1) + " seconds")
            print("\n\n")
        except json.JSONDecodeError:
            print("YOUR JOB JSON OF " + message + "IS INVALID")
            #Invalid request
            abort(403)
        print(job_json)
        job : Job = Job.create_with_json(job_json)
        print("RECIEVED MESSAGE TO ADD JOB WITH ID " + job_json["jobId"])
        #Call the database function to execute the insert
        #we complete the jobs data before returning it to the client
        #NOTE: Needs to be acid
        try:
            completeJob: Job = JobTable.add_job_with_foreign_keys(job, user_id)
        except DuplicateUserJob:
            abort(409) 
        assert(completeJob.company is not None)
        print("============== END ADD JOB ================")
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
        print("=============== BEGIN READ MOST RECENT JOB =================")
        #Call the database function to select and sort to the most recent job
        job : Job | None = JobTable.read_most_recent_job()
        if not job:
            #Not found
            print("DB IS EMPTY")
            abort(404)
        print("RETURNING RESULT")
        print("=============== END READ MOST RECENT JOB =================")
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
        print("=============== BEGIN READ JOB BY ID =================")
        #Grab the jobId from the request, it is in the form of a string
        try:
            job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        except:
            #invalid request
            print("Your request of: " + request)
            abort(403)
        print("JOB ID:  " + job_id)
        job : Job | None = JobTable.read_job_by_id(job_id)
        if not job:
            print("JOB NOT IN DB")
            abort(404)
        print("=============== END READ JOB BY ID =================")
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
        print("=============== BEGIN UPDATE JOB BY ID =================")
        #We take an argument of the whole job data in the from a json string
        try:
            message : str = request.args.get('jobJson', default="NO JOB JSON LOADED", type=str)
            job_json : Dict = json.loads(message)
            job : Job = Job.create_with_json(job_json)
        except json.JSONDecodeError:
            print("YOUR JOB JSON OF " + request + "IS INVALID")
            #Invalid request
            abort(403)
        JobTable.update_job(job)
        print("=============== END UPDATE JOB BY ID =================")
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
        print("=============== BEGIN DELETE JOB BY ID =================")
        #Get the job id from the request
        try:
            job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        except:
            print("Request of: " + request + " is invalid")
            #Invalid request
            abort(403)
        #run the sql code
        JobTable.delete_job_by_id(job_id)
        print("=============== END DELETE JOB BY ID =================")
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
            print("Request of: " + request + " is invalid")
            #Invalid request
            abort(403)
        print("Recieved message to read company: " + company)
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
        print("=============== BEGIN GET USER DATA =================")
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
        print("=============== END GET USER DATA =================")
        return json.dumps(return_json)
    @app.route('/databases/update_user_job', methods=["POST"])
    def update_user_job():
        print("=============== BEGIN UPDATE USER JOB =================")
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            print("Couldn't find user")
            abort(404)
        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        if (job_id == "NO JOB ID LOADED"):
            print("Couldn't find job")
            abort(400)
        update_json = request.get_json()["updateDict"]
        return json.dumps(UserJobTable.update_user_job(job_id, user.user_id, update_json).to_json())  
    @app.route('/databases/delete_user_job', methods=["POST"])
    @token_required
    def delete_user_job():
        print("=============== BEGIN DELETE USER JOB =================")
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            print("Couldn't find user")
            abort(404)
        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        if (job_id == "NO JOB ID LOADED"):
            print("Couldn't find job")
            abort(400)
        UserJobTable.delete_user_job(user.user_id, job_id)
        print("=============== END DELETE USER JOB =================")
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
        print("=============== BEGIN DELETE USER =================")
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
        print("=============== END DELETE USER =================")
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
        print("=============== BEGIN UPDATE USER PREFERENCES =================")
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        updateJson: Dict = request.get_json()["updateJson"]
        newPreferences: UserPreferences = UserPreferencesTable.update_user_preferences(updateJson, user.user_id)
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
        print("=============== BEGIN UPDATE USER LOCATION =================")
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
            return json.dumps(newLocation.to_json())
        else:
            location: Location = Location.try_get_location_from_json(updateJson)
            UserLocationTable.add_user_location(location, user.user_id)
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
        print("=============== BEGIN DELETE USER LOCATION =================")
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        UserLocationTable.delete_location(user.user_id)
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
        print("=============== BEGIN ADD RESUME =================")
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        request_json: Dict = request.get_json()
        resume_json: Dict = request_json["resume"]
        #Check for the key first to make sure theres no keyError and then check to make sure its true
        if "replace" in request_json and request_json["replace"]:
            print("REPLACING RESUME")
            ResumeTable.delete_resume(request_json["oldId"])
        resume: Resume = Resume.create_with_json(resume_json)
        resume.user_id = str(user.user_id)
        resume_json: Dict = ResumeTable.add_resume(user.user_id, resume)
        print("=============== END ADD RESUME =================")
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
        print("=============== BEGIN DELETE RESUME =================")
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        resume_id: str = request.args.get('resumeId', default="NO RESUME LOADED", type=str)
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        ResumeTable.delete_resume(resume_id)
        print("=============== END DELETE RESUME =================")
        return 'success', 200
    @app.route('/databases/read_resume', methods=['GET'])
    @token_required
    def read_resume():
        print("=============== BEGIN READ RESUME =================")
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        resume_id: str = request.args.get('resumeId', default="NO RESUME LOADED", type=str)
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if resume:
            return json.dumps(resume.to_json())
        print("=============== END READ RESUME =================")
        return "Could not find resume with id", 404
    @app.route('/databases/update_resume', methods=['POST'])
    @token_required
    def update_resume():
        print("=============== BEGIN UPDATE RESUME =================")
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
        print("=============== END UPDATE RESUME =================")
        return json.dumps(ResumeTable.update_resume_by_id(resume_id, user.user_id, update_json).to_json())
    '''
    compare_resumes

    compares all users resumes in the db against a job description
    '''
    @app.route('/databases/compare_resumes', methods=['POST'])
    @token_required
    def compare_resumes():
        print("=============== BEGIN COMPARE RESUMES =================")
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
        print("=============== END COMPARE RESUMES =================")
        return json.dumps(resume_comparison_data) 
    '''
    compare_resumes_by_id

    User sends id of resume to compare, we read it from the db, and then compare it
    '''
    @app.route('/databases/compare_resumes_by_id', methods=['POST'])
    @token_required
    def compare_resumes_by_id():
        print("=============== BEGIN COMPARE RESUMES BY ID =================")
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
        print("=============== END COMPARE RESUMES BY ID =================")
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
        print("=============== BEGIN GET SPECIFIC RESUME COMPARISON =================")
        token : str = request.headers.get('Authorization')
        print("Got request to get specific resume comparison")
        user : User | None = decode_user_from_token(token)

        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        resume_id : str = request.args.get('resumeId', default="NO RESUME ID LOADED", type=str)
        print({"job_id": job_id})
        print({"resume_id": resume_id})
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            print("Resume not found")
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            print("Invalid Id")
            return 'Invalid Id', 403
        resume_comparison = ResumeComparisonCollection.read_specific_resume_comparison(job_id, resume_id)
        if not resume_comparison:
            print("Could not find resume comparison with ids")
            return "Could not find resume comparison with ids", 404
        #Remove mongodb id
        del resume_comparison["_id"]
        print("=============== END GET SPECIFIC RESUME COMPARISON =================")
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
        print("=============== BEGIN COMPARE RESUME FROM REQUEST =================")
        #is this double the db work because we're getting the user twice?
        #once from token required, once from this
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        req_json = request.get_json()
        job_id = req_json["jobId"]
        job_description: str = req_json["jobDescription"]
        print("Loaded job description")
        resume_json: Dict = request.get_json()["resume"]
        resume: Resume = Resume.create_with_json(resume_json)
        print("got resumes")
        resume_comparison_data = ResumeComparison.get_resume_comparison_dict(job_description, job_id, resume, user.user_id)
        #Not going to add these to db, pretty much just for debugview
        print("Returning data")
        print("=============== END COMPARE RESUME FROM REQUEST =================")
        return json.dumps(resume_comparison_data) 
    
    @app.route('/databases/compare_resume_by_ids', methods=['GET'])
    @token_required
    def compare_resume_by_ids():
        print("=============== BEGIN COMPARE RESUME BY IDS =================")
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        job_id : str = request.args.get('jobId', default="NO JOB ID LOADED", type=str)
        resume_id : str = request.args.get('resumeId', default="NO RESUME ID LOADED", type=str)
        reread_resume: Resume = ResumeTable.read_resume_by_id(resume_id)
        if not reread_resume:
            print(f"Could not find resume with id: {resume_id}")
            return "Resume not found", 404
        if (str(reread_resume.user_id) != str(user.user_id)):
            return 'Invalid Id', 403
        job : Job = JobTable.read_job_by_id(job_id)
        if not job:
            print(f"Could not find job with id: {job_id}")
            return "Job not found", 404
        resume_comparison_data = ResumeComparison.get_resume_comparison_dict(job.description, job_id, reread_resume, user.user_id)
        ResumeComparisonCollection.add_resume_comparison(resume_comparison_data)
        #Remove mongodb id
        del resume_comparison_data["_id"]
        print("=============== END COMPARE RESUME BY IDS =================")
        return json.dumps(resume_comparison_data)
    @app.route('/api/verify_address', methods=['GET'])
    def verify_address():
        print("=============== BEGIN VERIFY ADDRESS =================")
        search_json: Dict = json.loads(request.args.get("searchJson"))
        if not search_json:
            return "No address sent", 400
        search_text: str = search_json["street"] + " " + search_json["city"] + " " + search_json["zipCode"] + " " + search_json["stateCode"]
        endpoint: str = "mapbox.places"
        #quoting to uri encode it
        mapbox_response: Dict = requests.get(f"https://api.mapbox.com/geocoding/v5/{endpoint}/{quote(search_text)}.json?access_token={MAPBOXKEY}").json()
        main_location: Dict = mapbox_response["features"][0]
        print("Verified location to:")
        print(main_location)
        print("=============== END VERIFY ADDRESS =================")
        try:
            return json.dumps({"coordinates": main_location["geometry"]["coordinates"]})
        except KeyError:
            return "invalid location", 400
    @app.route('/api/directions', methods=['GET'])
    @token_required
    def get_directions():
        print("=============== BEGIN GET DIRECTIONS =================")
        origin_lat = request.args.get('originLat')
        origin_lng = request.args.get('originLng')
        dest_lat = request.args.get('destLat')
        dest_lng = request.args.get('destLng')
        if not origin_lat or not origin_lng or not dest_lat or not dest_lng:
            print("MISSING PARAMETERS! Cannot get directions")
            return json.dumps({'message': 'Missing required parameters'}), 400
        responseJson = LocationFinder.get_directions(origin_lat, origin_lng, dest_lat, dest_lng)
        if not responseJson:
            return json.dumps({'message': 'Failed to grab location'}), 400
        responseJsonReversed = LocationFinder.get_directions(dest_lat, dest_lng, origin_lat, origin_lng, returning=True)
        responseJson["leavingDuration"] = responseJsonReversed["arrivingDuration"]
        responseJson["leavingTrafficDuration"] = responseJsonReversed["arrivingTrafficDuration"]
        print("=============== END GET DIRECTIONS =================")
        return json.dumps(responseJson), 200
    @app.route('/api/get_relocation_data', methods=['POST'])
    @token_required
    def get_relocation_data():
        print("=============== BEGIN GET RELOCATION DATA =================")
        req_json = request.get_json()
        location_json = req_json["location"]
        location = Location.try_get_location_from_json(location_json)
        print("LOADED LOCATION!")
        print(json.dumps(location_json, indent=2))
        if not location:
            print("Failed to get location from request body")
            return json.dumps({'message': 'Missing required parameters'}), 400
        relocation_data = asyncio.run(RelocationDataGrabber.get_data(location))
        return json.dumps(relocation_data), 200
    @app.route('/api/verify_token', methods=['GET'])
    def verify_token():
        token : str = request.headers.get('Authorization')
        print(token)
        try:
            user : User | None = decode_user_from_token(token)
            if user:
                return "AUTHED", 200
            else:
                return "NO_AUTH", 200
        except:
            return "NO_AUTH", 200
    @app.route('/api/get_directions', methods=['GET'])
    def shutdown():
        print("Handling database server shutdown")
        HelperFunctions.handle_sigterm("database_server")
        print("Shutdown successful")
    def run():
        print("Running server")
        try:
            app.run(debug=False, host=HOST, port=PORT, ssl_context=(os.path.join(os.getcwd(), "cert.pem"), os.path.join(os.getcwd(), "key.pem")))
        except:
            DatabaseServer.shutdown()
            
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
