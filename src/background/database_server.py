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
    format='%(asctime)s %(levelname)s %(process)d: %(message)s',
)

from flask import Flask, abort, request, Response, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from google.oauth2 import id_token
import random
import uuid
from uuid import UUID
from dotenv import load_dotenv
from auth_logic import get_token
from payment_decorators import PaymentDecorators
import jwt
import json
from mailing import Mailing
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
from keyword_table import KeywordTable
from email_confirmation_table import EmailConfirmationTable
from user_subscription_table import UserSubscriptionTable, UserSubscription
from user_free_data_table import UserFreeDataTable
from user import UserInvalidData
from resume_nlp.resume_comparison import ResumeComparison
from resume_comparison_collection import ResumeComparisonCollection
from feedback_collection import FeedbackCollection
from location_finder import LocationFinder
from relocation_data_grabber import RelocationDataGrabber
from company import Company
from job import Job
from user import User
from resume import Resume
from location import Location
from subcription import Subscription
from typing import Dict
import glassdoor_scraper
from helper_functions import HelperFunctions
import stripe
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
WEBSITE_URL = "https://applicantiq.org" if os.environ["SERVER_ENVIRONMENT"] == "production" else "http://localhost:8080"

CANSCRAPEGLASSDOOR: bool = True
MAPBOXKEY: str = os.environ["MAPBOX_KEY"]
API_KEY : str = os.environ["GOOGLE_API_KEY"]
STRIPE_TEST_API_KEY : str = os.environ["STRIPE_TEST_KEY_PRIVATE"]
STRIPE_API_KEY : str = os.environ["STRIPE_KEY_PRIVATE"]
#using get to not cause keyErrors on local machine
STRIPE_FULFILL_ORDER_KEY : str = os.environ["STRIPE_FULFILL_ORDER_KEY"] if os.environ["STRIPE_ENVIRONMENT"] == "production" else os.environ.get("STRIPE_FULFILL_ORDER_KEY_TEST")
STRIPE_RENEW_ORDER_KEY : str = os.environ["STRIPE_RENEW_ORDER_KEY"] if os.environ["STRIPE_ENVIRONMENT"] == "production" else os.environ.get("STRIPE_RENEW_ORDER_KEY_TEST")
STRIPE_CANCEL_ORDER_KEY : str = os.environ["STRIPE_CANCEL_ORDER_KEY"] if os.environ["STRIPE_ENVIRONMENT"] == "production" else os.environ.get("STRIPE_CANCEL_ORDER_KEY_TEST")

if os.environ["SERVER_ENVIRONMENT"] == "development":
    STRIPE_FULFILL_ORDER_KEY = os.environ["STRIPE_LOCAL_WEBHOOK"]
    STRIPE_RENEW_ORDER_KEY = os.environ["STRIPE_LOCAL_WEBHOOK"]
    STRIPE_CANCEL_ORDER_KEY = os.environ["STRIPE_LOCAL_WEBHOOK"]

stripe.api_key = STRIPE_API_KEY if os.environ["STRIPE_ENVIRONMENT"] == "production" else STRIPE_TEST_API_KEY

ADDUSERJOBBYDEFAULT = False

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

        logging.info("ADDING FREE DATA TO DB")
        if (UserFreeDataTable.read_free_data_by_email(user.email)):
            logging.info("USER IS BEING A SNEAKY LIL SNEAKSTER AND ALREADY HAS FREE DATA IN OUR DB")
            UserFreeDataTable.reassign_free_data(str(user_id), user.email)
        else:
            UserFreeDataTable.add_free_data(user_id)
        logging.info("ADDED FREE DATA TO DB")

        token, expiration_date = get_token(user)

        logging.info("Setting userId to " + user_id)
        logging.info("Setting token to " + token)

        Mailing.send_html_email("You're signed up!", Mailing.get_html_from_file("signup"), user.email)

        logging.info(f"============== END REQUEST TO REGISTER TOOK {time.time() - st} seconds ================")
        return jsonify({'token': token, 'userId': user_id, 'expirationDate': expiration_date})
    #########################################################################################
    #
    #
    # JOB METHODS
    #
    #
    #########################################################################################
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
            add_user_job = request.args.get("addUserJob", type=bool, default=False)
            logging.info("CHECKING IF WE NEED TO SCRAPE GLASSDOOR")
            shouldScrape = False
            company : Company | None = CompanyTable.read_company_by_id(company_name)
            if not company:
                shouldScrape = True
            #Symbolic empty company
            if not company or not company.overall_rating or company.overall_rating < 0.1:
                shouldScrape = True
            if (shouldScrape and CANSCRAPEGLASSDOOR and not message["noCompanies"]):
                if (not message["gdPageSource"]):
                    job_json["company"] = Company(company_name, 0, 0, 0, 0, 0, 0, 0, 0, 0, None).to_json()
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
                if message["noCompanies"]:
                    logging.info("No companies found")
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
            completeJob: Job = JobTable.add_job_with_foreign_keys(job, user_id, add_user_job=add_user_job)
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
    ##########################################################################################
    #
    #
    # COMPANY METHODS
    #
    #
    ##########################################################################################
    #Used for the client to read the company or add the company data
    '''
    read_company_by_name

    responds to request and gets a companys data by name

    args:
        request
            company: str company name
    returns
        company json
    '''
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
        #Symbolic empty company
        if not company.overall_rating or company.overall_rating < 0.1:
            abort(404)
        return company.to_json()
    @app.route('/databases/add_company_with_source', methods=["POST"])
    @token_required
    def add_company_with_source():
        try:
            company_name : str = request.get_json()['companyName']
            company_source : str = request.get_json()['companySource']
            company_data_url : str = request.get_json()['companyDataUrl']
        except:
            logging.error("Request of: " + request + " is invalid")
            #Invalid request
            abort(403)
        company_dict: Dict = glassdoor_scraper.get_company_from_page_source(company_source, company_data_url)
        company_dict["companyName"] = company_name
        company: Company = Company.create_with_json(company_dict)
        logging.info("Recieved message to add company: " + company.company_name)
        if not company:
            abort(404)
        reread_company = CompanyTable.read_company_by_id(company.company_name)
        if not reread_company:
            CompanyTable.add_company(company)
            logging.info("COMPANY SUCCESSFULLY ADDED")
        else:
            logging.info("COMPANY ALREADY IN DB")
            if reread_company.isEmpty() and not company.isEmpty():
                CompanyTable.update_company(company)
                logging.info("COMPANY DETAILS UPDATED IN DB")
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
    #Not the most restful but returns the full list of jobs for a us
    @app.route('/databases/add_user_job', methods=["POST"])
    @token_required
    def add_user_job():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO ADD USER JOB ================")
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
        
        addedJob: Job = UserJobTable.add_user_job(user.user_id, job_id)
        logging.info(f"=============== END ADD USER JOB TOOK {time.time() - st} seconds=================")
        return json.dumps(addedJob.to_json())

    @app.route('/databases/update_user_job', methods=["POST"])
    @token_required
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
        
        userSubscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)

        if userSubscription and userSubscription.is_active:
            stripe.Subscription.modify(
                userSubscription.stripe_subscription_id,
                cancel_at_period_end=True,
            )

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
    update_user_keywords

    updates a users preferences when passed a json dictionary containing a list of positive keywords and a list
    of negative keywords

    Full lists must be passed, its not a delta

    args:
        request
            body["positiveKeywords"]
            body["negativeKeywords"]
    returns:
        "success"
    '''
    @app.route('/databases/update_user_keywords', methods=['POST'])
    @token_required
    def update_user_keywords():
        #start time
        st = time.time()
        logging.info("============== GOT REQUEST TO UPDATE USER KEYWORDS ================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        if not token:
            return 'No token recieved', 401
        user : User | None = decode_user_from_token(token)
        if not user:
            return 'Invalid Token', 401
        positive_keywords: Dict = request.get_json()["positiveKeywords"]
        negative_keywords: Dict = request.get_json()["negativeKeywords"]
        KeywordTable.update_keywords(str(user.user_id), positive_keywords, negative_keywords)
        logging.info(f"============== END REQUEST TO UPDATE USER KEYWORDS {time.time() - st} seconds================")
        return "success", 200
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
    ##########################################################################################
    #
    #
    # RESUME METHODS
    #
    #
    ##########################################################################################
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
    @PaymentDecorators.check_subscription_for_resume_upload
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
    #############################################################################################
    #
    #
    # Resume Comparison Routes
    #
    #
    #############################################################################################
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
    @PaymentDecorators.check_subscription_for_resume_rating
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
    @PaymentDecorators.check_subscription_for_resume_rating
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
    ##################################################################################################
    #
    #
    # SUBSCRIPTION ROUTES
    #
    #
    #################################################################################################
    @app.route('/databases/get_subscription', methods=['GET'])
    @token_required
    def get_subscription():
        logging.info("=============== GOT REQUEST TO GET SUBSCRIPTION =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        user_subscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)
        if not user_subscription:
            return json.dumps({}), 200
        return json.dumps(user_subscription.to_json()), 200
    ##################################################################################################
    #
    #
    # Feedback routes
    #
    #
    #################################################################################################
    @app.route('/databases/submit_feedback', methods=['POST'])
    @token_required
    def submit_feedback():
        logging.info("=============== GOT REQUEST TO ADD FEEDBACK =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        feedback: Dict = request.get_json()
        feedback["userId"] = str(user.user_id)
        FeedbackCollection.add_feedback(feedback)
        return "success", 200
    ##################################################################################################
    #
    #
    # LOCATION ROUTES
    #
    #
    #################################################################################################
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
    @PaymentDecorators.pro_subscription_required
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
        response_json, other_way_arriving_json, response_json_reversed, other_way_returning_json = asyncio.run(LocationFinder.run_all_directions_queries_in_parallel(origin_lat, origin_lng, dest_lat, dest_lng))
        if not response_json:
            return json.dumps({'message': 'Failed to grab location'}), 400
        response_json["leavingDuration"] = response_json_reversed["arrivingDuration"]
        response_json["leavingTrafficDuration"] = response_json_reversed["arrivingTrafficDuration"]
        LocationFinder.add_traffic_directions(response_json, other_way_arriving_json, other_way_returning_json)
        logging.info("=============== END GET DIRECTIONS =================")
        return json.dumps(response_json), 200
    @app.route('/api/get_relocation_data', methods=['POST'])
    @PaymentDecorators.pro_subscription_required
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
    ##################################################################################################
    #
    #
    # EMAIL CONFIRMATION ROUTES
    #
    #
    #################################################################################################
    @app.route('/api/send_email_confirmation', methods=['POST'])
    def send_email_confirmation():
        logging.info("=============== BEGIN SEND CONFIRMATION EMAIL =================")
        logging.info(request.url)
        email = request.args.get('email')
        forgot_password = request.args.get('forgotPassword', type=bool, default=False)
        if forgot_password:
            logging.info("Forgot Password is true")
        if forgot_password:
            user: User = UserTable.read_user_by_email(email)
            if not user:
                return "User not found!", 404
        confirmation_code = str(random.randint(0, 999999)).zfill(6)
        EmailConfirmationTable.add_confirmation_code(email, confirmation_code, forgot_password=forgot_password)
        try:
            Mailing.send_confirmation_email(email, confirmation_code, forgot_password)
        except:
            return "Failed to send confirmation code", 400
        logging.info("=============== END SEND CONFIRMATION EMAIL =================")
        return "success", 200
    
    @app.route('/api/evaluate_email_confirmation', methods=['POST'])
    def evaluate_email_confirmation():
        logging.info("=============== BEGIN EVALUATE EMAIL CONFIRMATION =================")
        logging.info(request.url)
        email = request.args.get('email')
        forgot_password = request.args.get('forgotPassword', type=bool, default=False)
        confirmation_code = request.args.get('confirmationCode')
        confirmation_data = EmailConfirmationTable.readConfirmationCode(email)
        if forgot_password:
            if not confirmation_data["ForgotPassword"]:
                logging.info("Confirmation entry is not marked as forgot password")
                return "Invalid Confirmation Code", 401
        if (not confirmation_data):
            logging.error("Couldn't find confirmation data")
            return "Invalid Email", 400
        if confirmation_code != confirmation_data["ConfirmationCode"]:
            logging.info(f"Confirmation code of {confirmation_code} does not match our code of {confirmation_data["ConfirmationCode"]}")
            return "Invalid Confirmation Code", 401
        if confirmation_data["CreatedAt"].timestamp() + 600 < time.time():
            return "Expired Code", 401
        if forgot_password:
            user: User = UserTable.read_user_by_email(email)
            if not user:
                logging.error("Couldn't find user")
                return "Invalid Confirmation Code", 401
            return str(get_token(user, num_hours=1, forgot_password=True)[0]), 200
        logging.info("=============== END EVALUATE CONFIRMATION EMAIL =================")
        return "success", 200
    ##################################################################################################
    #
    #
    # RESET PW
    #
    #
    #################################################################################################
    @app.route('/api/reset_password', methods=['POST'])
    def reset_password():
        logging.info("=============== BEGIN RESET PASSWORD =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        try:
            payload: Dict[str, any] = jwt.decode(token, os.environ["secret_key"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError as e:
            return "Token Expired!", 403
        except jwt.InvalidTokenError as e:
            logging.error(f"token: {token}")
            logging.error("Token is invalid cannot reset password")
            return "Invalid Token!", 403
        if not payload.get("forgotPassword", False):
            logging.error(f"payload: {payload}")
            logging.error("Token does not specify forgotPassword, cannot reset password")
            return "Invalid Token!", 403
        new_password = request.get_json()["newPassword"]
        if not new_password:
            return "No password sent", 400
        email = payload["email"]
        user = UserTable.read_user_by_email(email)
        UserTable.reset_user_password(user.user_id, new_password)
        logging.info("=============== END RESET PASSWORD =================")
        return "success", 200
    ##################################################################################################
    #
    #
    # STRIPE ROUTES
    #
    #
    #################################################################################################
    @app.route('/payment/create-checkout-session', methods=['POST'])
    @token_required
    def create_checkout_session():
        logging.info("=============== BEGIN CREATE CHECKOUT SESSION =================")
        logging.info(request.url)
        subscription_type: str = request.args.get("subscriptionType", default=None)
        discount_code: str = request.args.get("discount", default=None)
        user = decode_user_from_token(request.headers["Authorization"])
        if not subscription_type:
            logging.info("Did not load subscription type aborting")
            abort(400)
        try:
            subsciption: Subscription
            if UserFreeDataTable.is_discountable(user.user_id):
                subsciption = Subscription(subscription_type, price=Subscription.PRO_SUBSCRIPTION_DISCOUNTED_PRICE, discount_code=discount_code)
            else:
                subsciption = Subscription(subscription_type, discount_code=discount_code)
        except ValueError:
            logging.info("Did not creaet subscription object aborting")
            abort(400)
        cur_subscription: UserSubscription = UserSubscriptionTable.read_subscription(str(user.user_id))
        if cur_subscription:
            if cur_subscription.subscription_object.subscription_type == subscription_type and cur_subscription.valid():
                logging.error("Found valid subscription, not allowing a second checkout")
                abort(400)
        logging.info("Loaded subscription")
        logging.info(subsciption.to_line_item())
        try:
            session: stripe.checkout.Session = stripe.checkout.Session.create(
                ui_mode = 'embedded',
                line_items=[
                    subsciption.to_line_item(),
                ],
                mode='subscription',
                return_url=WEBSITE_URL + '/completedPayment?session_id={CHECKOUT_SESSION_ID}',
                automatic_tax={'enabled': True},
                metadata={
                    'token': request.headers["Authorization"],
                    'subscriptionType': subscription_type
                }
            )
        except Exception as e:
            return str(e)

        return jsonify(clientSecret=session.client_secret)

    @app.route('/payment/session-status', methods=['GET'])
    @token_required
    def session_status():
        logging.info("=============== BEGIN GET CHECKOUT SESSION =================")
        logging.info(request.url)
        session: stripe.checkout.Session = stripe.checkout.Session.retrieve(request.args.get('session_id'))
        logging.info(json.dumps(session, indent=2))
        return jsonify(status=session.status, customer_email=session.customer_details.email, created_at=session.created)
    
    @app.route('/payment/send_message_to_cancel', methods=['POST'])
    @token_required
    def send_message_to_cancel():
        logging.info("=============== BEGIN SEND MESSAGE TO CANCEL =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        userSubscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)
        if not userSubscription:
            return json.dumps({"error": "No subscription found"}), 404
        stripe.Subscription.modify(
            userSubscription.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        UserSubscriptionTable.cancel(userSubscription.stripe_subscription_id)
        return "success", 200
    @app.route('/payment/send_message_to_restart', methods=['POST'])
    @token_required
    def send_message_to_restart():
        logging.info("=============== BEGIN SEND MESSAGE TO RESTART SUBSCRIPTION =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        userSubscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)
        if not userSubscription:
            return json.dumps({"error": "No subscription found"}), 404
        stripe.Subscription.modify(
            userSubscription.stripe_subscription_id,
            cancel_at_period_end=False,
        )
        UserSubscriptionTable.restart(userSubscription.stripe_subscription_id)
        return "success", 200
    @app.route('/payment/fulfill', methods=['POST'])
    def fulfill_subscription():
        logging.info("+++++++++++++++++++++++++++ STRIPE WEBHOOK ++++++++++++++++++++++++++++")
        logging.info("--------------------------- FULFILL PAYMENT --------------------------")
        logging.info(request.url)
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        event = None
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_FULFILL_ORDER_KEY
            )
            logging.info(event['type'])
        except ValueError as e:
            # Invalid payload
            logging.error("INVALID PAYLOAD")
            return jsonify({'error': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logging.error("INVALID SIGNATURE")
            return jsonify({'error': 'Invalid signature'}), 400

        if event['type'] in ['checkout.session.completed', 'checkout.session.async_payment_succeeded']:
            try:
                user_subscription: UserSubscription = UserSubscriptionTable.fulfill_checkout(event['data']['object']['id'])
                user: User = UserTable.read_user_by_id(str(user_subscription.user_id))
                Mailing.send_html_email("You're Officially a Pro", Mailing.get_html_from_file("prosignup"), user.email, variables={"FIRST_NAME": user.first_name})
            except RuntimeError as e:
                logging.error(e)
                logging.error("Payment not recieved")
                return jsonify({'error': 'Payment not recieved'}), 400
        else:
            logging.info("Event type not matched")

        return jsonify({'status': 'success'}), 200
    
    @app.route('/payment/cancel_subscription', methods=['POST'])
    def cancel_subscription():
        logging.info("+++++++++++++++++++++++++++ STRIPE WEBHOOK ++++++++++++++++++++++++++++")
        logging.info("--------------------------- CANCEL PAYMENT --------------------------")
        logging.info(request.url)
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        event = None
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_CANCEL_ORDER_KEY
            )
            logging.info(event['type'])
        except ValueError as e:
            # Invalid payload
            logging.error("INVALID PAYLOAD")
            return jsonify({'error': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logging.error("INVALID SIGNATURE")
            return jsonify({'error': 'Invalid signature'}), 400

        if event['type'] in ['customer.subscription.deleted']:
            try:
                stripe_subscription_id = event['data']['object']['id']
                user_subscription: UserSubscription = UserSubscriptionTable.read_subscription_by_stripe_sub_id(stripe_subscription_id)
                user: User = UserTable.read_user_by_id(str(user_subscription.user_id))
                Mailing.send_html_email("We're sorry to see you go!", Mailing.get_html_from_file("canceled"), user.email)
                ResumeTable.clear_resumes_after_subscription_end(user.user_id)
            except RuntimeError as e:
                logging.error(e)
                return jsonify({'error': 'Could not cancel subscription'}), 500
        else:
            logging.info("Event type not matched")

        return jsonify({'status': 'success'}), 200

    @app.route('/payment/renew_subscription', methods=['POST'])
    def renew_subscription():
        logging.info("+++++++++++++++++++++++++++ STRIPE WEBHOOK ++++++++++++++++++++++++++++")
        logging.info("--------------------------- RENEW PAYMENT --------------------------")
        logging.info(request.url)
        payload = request.data
        sig_header = request.headers.get('Stripe-Signature')
        event = None
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_RENEW_ORDER_KEY
            )
            logging.info(event['type'])
        except ValueError as e:
            # Invalid payload
            logging.error("INVALID PAYLOAD")
            return jsonify({'error': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logging.error("INVALID SIGNATURE")
            return jsonify({'error': 'Invalid signature'}), 400
        if event['type'] == "invoice.paid":
            logging.debug(json.dumps(event, indent=2))
            logging.info("=========== RENEWING SUBSCRIPTION ===========")
            invoice_data = event['data']['object']
            logging.info(json.dumps(invoice_data, indent=2))  # This is the invoice object
            subscription_id = invoice_data.get('subscription')
            try:
                new_subscription: UserSubscription = UserSubscriptionTable.renew(subscription_id)
            except Exception as e:
                #TO DO: handle this
                #send email debug etc
                return jsonify({'error': e}), 400
            logging.debug(json.dumps(new_subscription.to_json(), indent=2))
        else:
            logging.info("Event type not matched")
        return jsonify({'status': 'success'}), 200
    ##################################################################################################
    #
    #
    # FREE DATA ROUTES
    #
    #
    #################################################################################################
    @app.route('/databases/get_free_data', methods=['GET'])
    @token_required
    def get_free_data():
        logging.info("=============== BEGIN GET FREE DATA =================")
        logging.info(request.url)
        token : str = request.headers.get('Authorization')
        user : User | None = decode_user_from_token(token)
        return jsonify(UserFreeDataTable.get_free_resume_info(user.user_id)), 200
    ##################################################################################################
    #
    #
    # VERIFY TOKEN
    #
    #
    #################################################################################################
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
    #################################################################################################
    def shutdown():
        logging.critical("Handling database server shutdown")
        HelperFunctions.handle_sigterm("database_server")
        logging.info("Shutdown successful")
    def run():
        logging.info("Running server")
        try:
            if os.getenv("SERVER_ENVIRONMENT") != "development":
                app.run(debug=False, host=HOST, port=PORT, ssl_context=(os.path.join(os.getcwd(), "cert.pem"), os.path.join(os.getcwd(), "key.pem")))
            else:
                logging.info("Running without ssl context")
                app.run(debug=False, host=HOST, port=PORT)
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
