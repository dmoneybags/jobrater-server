#© 2024 Daniel DeMoney. All rights reserved.
from decimal import Decimal
from enum import Enum, IntEnum
from datetime import datetime
from company import Company
from location import Location
from mysql.connector.types import RowType, RowItemType
from typing import Dict
from location_finder import LocationFinder
from user_specific_job_data import UserSpecificJobData
import zlib

class JobInvalidData(Exception):
        def __init__(self, data: any, message : str ="INVALID DATA PASSED TO CONSTRUCTOR"):
            self.message = message + "DATA RECIEVED: " + str(message)
            super().__init__(self.message)

class PaymentFrequency(Enum):
    '''
    PaymentFrequency

    helper class for payment frequencies
    '''
    HOURLY = 1
    YEARLY = 2
class Mode(IntEnum):
    '''
    Mode

    helper class for job in person modes
    '''
    REMOTE = 1
    HYBRID = 2
    ONSITE = 3

class Job:
    '''
    __init__

    creates a job object with the given data
    
    args:
        job_id: the job_id from the linkedIn url
        applicants: the number of applicants scraped from linkedin
        career_stage: the career stage scraped from linkedin
        job_name: the job name scraped from linkedin
        company: a fully formed company object, optional, can create job without company
        payment_base: low end of a salary range ex: 100,000 -> 130,000 payment base is 100,000
        payment_freq: custom paymentFrequency object in the enum defined above
        payment high: ex: 100,000 -> 130,000 payment high is 130,000
        location_str: location string scraped from linkedin
        mode: custom mode object from the enum defined above, represents the jobs WFH policy
        seconds_posted_ago: the number of seconds since the job was posted
        time_added: date_time that we added the job to our db
        location_object: Optional the location object correlating to the jobs location from google places
    returns:
        job object with given data
    '''
    def __init__(self, job_id : str, applicants : int | None, career_stage : str, job_name : str, company : Company | None, 
                 description: str, payment_base : Decimal | None, payment_freq : PaymentFrequency | None, payment_high : Decimal | None, location_str : str,
                 mode: Mode, job_posted_at : datetime, time_added : datetime, location_object : Location | None,
                 user_specific_job_data: UserSpecificJobData | None = None) -> None:
        self.job_id : str = job_id
        assert(self.job_id is not None)
        self.applicants : int = applicants
        self.career_stage : str = career_stage
        self.job_name : str = job_name
        self.company : Company | None = company
        self.description : str = description
        self.payment_base : Decimal | None = payment_base
        self.payment_freq : PaymentFrequency | None = payment_freq
        self.payment_high : Decimal | None = payment_high
        self.location_str : str | None = location_str
        self.mode : Mode = mode
        self.job_posted_at : datetime = job_posted_at
        self.time_added : datetime = time_added
        self.location_object : Location = location_object
        self.user_specific_job_data : UserSpecificJobData = user_specific_job_data
    '''
    str_to_mode

    turns a str mode into a Mode type mode

    args:
        mode_str: the mode string (usually loaded from sql database or json request)
    returns:
        Mode object
    '''
    def str_to_mode(mode_str : str) -> Mode | None:
        if not mode_str:
            return None
        mode_strs : list[str] = ["Remote", "Hybrid", "On-site"]
        enum_value : int = mode_strs.index(mode_str) + 1
        return Mode(enum_value)
    '''
    payment_frequency_to_str

    turns a payment freq object into a str for serialization

    args:
        payment_frequency: payment_freq, the payment_freq object
    returns:
        payment_freq str
    '''
    def payment_frequency_to_str(payment_freq: PaymentFrequency) -> str:
        payment_freq_list : list[str] = ["hr", "yr"]
        return payment_freq_list[payment_freq.value - 1]
    '''
    payment_freq_to_mode

    turns a str mode into a payment_freq type

    args:
        payment_freq_str: the string
    returns:
        PaymentFrequency object
    '''
    def str_to_payment_frequency(payment_freq_str : str | None) -> Mode | None:
        if payment_freq_str is None:
            return None
        payment_freq_list : list[str] = ["hr", "yr"]
        enum_value : int = payment_freq_list.index(payment_freq_str) + 1
        return PaymentFrequency(enum_value)
    '''
    mode_to_str

    turns a mode object into a str for serialization

    args:
        mode: Mode, the mode object
    returns:
        mode str
    '''
    def mode_to_str(mode: Mode) -> str | None:
        if not mode:
            return None
        mode_strs : list[str] = ["Remote", "Hybrid", "On-site"]
        return mode_strs[mode.value - 1]
    '''
    create_with_sql_row

    creates a job object from a sql row returned from the cursor

    args:
        sql_query_row result of a cursor executing a select
    returns:
        Job object
    '''
    @classmethod
    def create_with_sql_row(cls, sql_query_row: (Dict[str, RowItemType])) -> 'Job':
        print("CREATING JOB WITH SQL ROW OF: ")
        print(sql_query_row)
        company : Company | None = Company.create_with_sql_row(sql_query_row)
        location : Location | None = Location.try_get_location_from_sql_row(sql_query_row)
        job_id : str = sql_query_row["JobId"]
        applicants : int | None = int(sql_query_row["Applicants"]) if sql_query_row["Applicants"] is not None else None
        career_stage : str = sql_query_row["CareerStage"]
        decompressed_bytes: bytes = zlib.decompress(sql_query_row["Description"])
        decompressed_description: str = decompressed_bytes.decode("utf-8")
        description : str = decompressed_description
        job_name : str = sql_query_row["Job"]
        payment_base : Decimal = sql_query_row["PaymentBase"]
        try:
            payment_freq : PaymentFrequency = Job.str_to_payment_frequency(sql_query_row["PaymentFreq"])
        except KeyError:
            payment_freq = None
        try:
            payment_high : Decimal = sql_query_row["PaymentHigh"]
        except KeyError:
            payment_high = None
        try:
            location_str : str = sql_query_row["LocationStr"]
        except KeyError:
            location_str = None
        mode : Mode = Job.str_to_mode(sql_query_row["Mode"])
        job_posted_at : datetime = sql_query_row["JobPostedAt"]
        time_added : datetime = sql_query_row["TimeAdded"]
        user_specific_job_data : UserSpecificJobData | None = None
        #Check if this is a job with userJob
        if "TimeSelected" in sql_query_row:
            user_specific_job_data = UserSpecificJobData.create_with_sql_row(sql_query_row)
        return cls(job_id, applicants, career_stage, job_name, company, description, payment_base, payment_freq, payment_high, location_str, mode, job_posted_at,
                   time_added, location, user_specific_job_data=user_specific_job_data)
    '''
    create_with_json

    creates a job object from json returned from request

    args:
        json from request
    returns:
        Job object
    '''
    #Could be much more patterned tbh
    #Optional logic is not consistent
    @classmethod
    def create_with_json(cls, json_object : Dict) -> 'Job':
        company : Company = Company.try_create_with_json(json_object["company"])
        location : Location | None = Location.try_get_location_from_json(json_object["location"])
        job_id : str = json_object["jobId"]
        applicants : int = int(json_object["applicants"]) if json_object["applicants"] is not None else None
        career_stage : str = json_object["careerStage"]
        description : str = json_object["description"]
        job_name : str = json_object["jobName"]
        try:
            payment_base : Decimal = json_object["paymentBase"]
        except KeyError:
            payment_base = None
        try:
            payment_freq : PaymentFrequency = Job.str_to_payment_frequency(json_object["paymentFreq"])
        except KeyError:
            payment_freq = None
        try:
            payment_high : Decimal = json_object["paymentHigh"]
        except KeyError:
            payment_high = None
        try:
            location_str : str = json_object["locationStr"]
        except KeyError:
            location_str = None
        mode : Mode = Job.str_to_mode(json_object["mode"])
        job_posted_at : datetime = datetime.fromtimestamp(json_object["jobPostedAt"])
        try:
            time_added : datetime = datetime.fromtimestamp(float(json_object["timeAdded"]))
        except (KeyError, TypeError):
            time_added = None
        user_specific_job_data : UserSpecificJobData | None = None
        #Check if this is a job with userJob
        if "timeSelected" in json_object:
            user_specific_job_data = UserSpecificJobData.create_with_json(json_object)
        return cls(job_id, applicants, career_stage, job_name, company, description, payment_base, payment_freq, payment_high, location_str, mode, job_posted_at,
                   time_added, location, user_specific_job_data=user_specific_job_data)
    '''
    to_json

    dumps job to json, includes all fks

    args:
        None
    returns:
        Dict
    '''
    def to_json(self) -> Dict:
        return {
            "jobId" : self.job_id,
            "applicants" : self.applicants,
            "careerStage" : self.career_stage,
            "jobName" : self.job_name,
            "company" : self.company.to_json(),
            "description" : self.description,
            "paymentBase": float(self.payment_base) if self.payment_base is not None else None,
            "paymentHigh": float(self.payment_high) if self.payment_high is not None else None,
            "paymentFreq" : Job.payment_frequency_to_str(self.payment_freq) if self.payment_freq else None,
            "locationStr" : self.location_str,
            "mode" : Job.mode_to_str(self.mode) if self.mode else None,
            "jobPostedAt" : int(self.job_posted_at.timestamp()) if self.job_posted_at is not None else None,
            "timeAdded" : int(self.time_added.timestamp()) if self.time_added is not None else None,
            "location" : self.location_object.to_json() if self.location_object else None,
            "userSpecificJobData" : self.user_specific_job_data.to_json() if self.user_specific_job_data else None
        }
    '''
    to_sql_friendly_json

    dumps job to json friendly for our sql queries where the company object is stored as 
    fk.

    args:
        None
    returns:
        Dict
    '''
    def to_sql_friendly_json(self) -> Dict:
        description_bytes: bytes = self.description.encode("utf-8")
        compressed_description: bytes = zlib.compress(description_bytes)
        sql_friendly_dict : Dict = {
            "jobId" : self.job_id,
            "applicants" : self.applicants,
            "careerStage" : self.career_stage,
            "job" : self.job_name,
            "description" : compressed_description,
            "company" : self.company.company_name,
            "paymentBase" : self.payment_base if self.payment_base else None,
            "paymentHigh": self.payment_high,
            "paymentFreq" : Job.payment_frequency_to_str(self.payment_freq) if self.payment_freq else None,
            "locationStr" : self.location_str,
            "mode" : Job.mode_to_str(self.mode) if self.mode else None,
            "jobPostedAt" : self.job_posted_at
        }
        return sql_friendly_dict
