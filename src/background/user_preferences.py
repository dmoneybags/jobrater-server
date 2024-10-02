#(c) 2024 Daniel DeMoney. All rights reserved.
from uuid import UUID
from decimal import Decimal
from job import PaymentFrequency, Job
from typing import Dict
from mysql.connector.types import RowType, RowItemType
import logging

class UserPreferences:
    '''
    UserPreferences

    A class representing a users self selected data, settings and preferences towards jobs and settings for the app

    Attributes:
        user_id: UUID the id of the user that the preferences correspond to
        desired_pay: Decimal the desired pay amount of the user 
            NOTE: this amount doesn't respresent too much without the payment frequency
            EXAMPLE:
                desired_pay: $40
                payment_freq: hr
                User wants desired_pay * 24 * 365 as a base value
        desired_payment_freq: PaymentFrequency the frequency at which desired pay is calculated
        desired_commute int the desired commute time in minutes 
        desires_remote bool whether or not the user desires a remote job
        desires_hybrid bool whether ot not the user desires a hybrid job
        auto_activate_on_new_job_loaded bool should the script scrape every new job or only on request?
        auto_compare_resume_on_new_job_loaded bool should the script compare your resume on every new job loaded
        save_every_job_by_default bool should the script save every job you look at to localStorage
    '''
    def __init__(self, user_id: UUID, desired_pay: Decimal, desired_payment_freq: PaymentFrequency,
                 desired_commute: int, desires_remote: bool, desires_hybrid: bool, desires_onsite: bool, desired_career_stage: str,
                 auto_activate_on_new_job_loaded: bool, auto_compare_resume_on_new_job_loaded: bool, save_every_job_by_default: bool) -> None:
        self.user_id: UUID = user_id
        self.desired_pay: Decimal = desired_pay
        self.desired_payment_freq: PaymentFrequency = desired_payment_freq
        #Minutes to get there one way
        self.desired_commute: int = desired_commute
        self.desires_remote: bool = desires_remote
        self.desires_hybrid: bool = desires_hybrid
        self.desires_onsite: bool = desires_onsite
        self.desired_career_stage: str = desired_career_stage
        self.auto_activate_on_new_job_loaded: bool = auto_activate_on_new_job_loaded
        self.auto_compare_resume_on_new_job_loaded: bool = auto_compare_resume_on_new_job_loaded
        self.save_every_job_by_default: bool = save_every_job_by_default
    '''
    create_from_sql_query_row

    creates a user preferences object from the output of a cursor fetch

    will error if there is missing user preferences data in the output

    Args:
        sql_query_row: the output of a cursor fetchone or fetchall
    returns:
        UserPreferences object
    '''
    @classmethod
    def create_from_sql_query_row(cls, sql_query_row: (Dict[str, RowItemType])) -> 'UserPreferences':
        if not sql_query_row["UserIdFk"]:
            #NOTE: will error here when in production
            return None
        user_id: UUID = UUID(sql_query_row["UserIdFk"])
        desired_pay: Decimal = sql_query_row["DesiredPay"]
        desired_payment_freq: PaymentFrequency = Job.str_to_payment_frequency(sql_query_row["DesiredPaymentFreq"])
        desired_commute: int = sql_query_row["DesiredCommute"]
        desires_remote: bool = sql_query_row["DesiresRemote"]
        desires_hybrid: bool = sql_query_row["DesiresHybrid"]
        desires_onsite: bool = sql_query_row["DesiresOnsite"]
        desired_career_stage: str = sql_query_row["DesiredCareerStage"]
        auto_activate_on_new_job_loaded: bool = sql_query_row["AutoActiveOnNewJobLoaded"]
        auto_compare_resume_on_new_job_loaded: bool = sql_query_row["AutoCompareResumeOnNewJobLoaded"]
        save_every_job_by_default: bool = sql_query_row["SaveEveryJobByDefault"]
        return cls(user_id, desired_pay, desired_payment_freq,
                 desired_commute, desires_remote, desires_hybrid, desires_onsite, desired_career_stage,
                 auto_activate_on_new_job_loaded, auto_compare_resume_on_new_job_loaded, save_every_job_by_default)
    '''
    try_create_from_sql_query_row

    Safer way of running create_from_sql_query_row, will return None instead of an error

    Args:
        sql_query_row: the output of a cursor fetchone or fetchall
    returns:
        UserPreferences object or None
    '''
    def try_create_from_sql_query_row(sql_query_row: (Dict[str, RowItemType])) -> 'UserPreferences':
        try:
            return UserPreferences.create_from_sql_query_row(sql_query_row)
        except KeyError:
            return None
    '''
    create_from_json

    Creates an instance from json

    will error if keys are missing

    Args:
        json_object Dict the json object to create the instance from 
    returns:
        UserPreferences object
    '''
    @classmethod
    def create_from_json(cls, json_object: Dict) -> 'UserPreferences':
        user_id: UUID = UUID(json_object["userId"]) if json_object["userId"] is not None else ""
        desired_pay: Decimal = json_object["desiredPay"]
        desired_payment_freq: PaymentFrequency = Job.str_to_payment_frequency(json_object["desiredPaymentFreq"])
        desired_commute: int = json_object["desiredCommute"]
        desires_remote: bool = json_object["desiresRemote"]
        desires_hybrid: bool = json_object["desiresHybrid"]
        desires_onsite: bool = json_object["desiresOnsite"]
        desired_career_stage: str = json_object["desiredCareerStage"]
        auto_activate_on_new_job_loaded: bool = json_object["autoActiveOnNewJobLoaded"]
        auto_compare_resume_on_new_job_loaded: bool = json_object["autoCompareResumeOnNewJobLoaded"]
        save_every_job_by_default: bool = json_object["saveEveryJobByDefault"]
        return cls(user_id, desired_pay, desired_payment_freq,
                 desired_commute, desires_remote, desires_hybrid, desires_onsite, desired_career_stage,
                 auto_activate_on_new_job_loaded, auto_compare_resume_on_new_job_loaded, save_every_job_by_default)
    '''
    try_create_from_json

    Again, just a safer way of running create from json
    '''
    def try_create_from_json(json_object: Dict) -> 'UserPreferences':
        try:
            return UserPreferences.create_from_json(json_object)
        except KeyError:
            return None
    '''
    to_json

    dumps preferences to json
    '''
    def to_json(self):
        return {
            "userId": str(self.user_id),
            "desiredPay": float(self.desired_pay),
            "desiredPaymentFreq" : Job.payment_frequency_to_str(self.desired_payment_freq),
            "desiredCommute": self.desired_commute,
            "desiresRemote": self.desires_remote,
            "desiresHybrid": self.desires_hybrid,
            "desiresOnsite": self.desires_onsite,
            "desiredCareerStage": self.desired_career_stage,
            "autoActiveOnNewJobLoaded": self.auto_activate_on_new_job_loaded,
            "autoCompareResumeOnNewJobLoaded": self.auto_compare_resume_on_new_job_loaded,
            "saveEveryJobByDefault": self.save_every_job_by_default
        }

        