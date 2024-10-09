#(c) 2024 Daniel DeMoney. All rights reserved.
from collections import OrderedDict
from database_functions import DatabaseFunctions, get_connection
from mysql.connector.errors import IntegrityError
import json
from uuid import UUID
from mysql.connector.cursor import MySQLCursor
from mysql.connector.connection_cext import CMySQLConnection
from job import Job
from user_specific_job_data import UserSpecificJobData
from typing import Dict
from mysql.connector.types import RowType, RowItemType
import hashlib
import logging


class UserJobTable:
    def generate_user_job_id(user_id: str, job_id: str, length: int = 36) -> str:
        """
        Generate a deterministic short hash (default length: 16) for the combination of user_id and job_id.

        Args:
            user_id: The string representation of the user's UUID.
            job_id: The string representation of the job id.
            length: The length of the generated hash (default is 16 characters).

        Returns:
            A truncated SHA-256 hash as a string.
        """
        hasher = hashlib.sha256()
        hasher.update((user_id + job_id).encode('utf-8'))
        return hasher.hexdigest()[:length]
    '''
    get_add_user_job_query

    gets the query to add a user_job into the db

    args:
        None
    returns:
        string query
    '''
    def __get_add_user_job_query() -> str:
        return """
            INSERT INTO UserJob (UserJobId, UserId, JobId) VALUES (%s, %s, %s)
        """
    def __get_update_user_job_by_id(update_dict: Dict) -> str:
        """
        Generates an SQL query string to update a UserJob in the database.

        Args:
            update_dict (Dict): Dictionary where keys are column names and values are the new data.

        Returns:
            str: The SQL query string to update the UserJob.
        """
        # Build the update string with column names and placeholders
        col_str: str = ', '.join([f"{col_name} = %s" for col_name in update_dict.keys()])
        
        return f"""
            UPDATE UserJob 
            SET {col_str}
            WHERE UserJobId = %s
        """
    '''
    get_delete_user_job_query

    gets the query to delete a user_job into the db

    args:
        None
    returns:
        string query
    '''
    def __get_delete_user_job_query() -> str:
        return """
            DELETE FROM UserJob WHERE UserJobId = %s
        """
    '''
    get_read_user_jobs_query

    gets the query to read a user_job from the db by user id

    args:
        None
    returns:
        string query
    '''
    def __get_read_user_jobs_query() -> str:
        return f"""
        SELECT *
        FROM UserJob
        JOIN Job ON UserJob.JobId = Job.JobId
        JOIN Company ON Job.Company = Company.CompanyName
        LEFT JOIN JobLocation ON Job.JobId = JobLocation.JobIdFK
        WHERE UserJob.UserId = %s
        ORDER BY UserJob.TimeSelected DESC;
        """
    def __get_read_specific_user_job_query() -> str:
        return f"""
        SELECT *
        FROM UserJob
        WHERE UserJobId = %s
        """
    def __get_read_specific_user_job_query_full_join() -> str:
        return f"""
        SELECT *
        FROM UserJob
        JOIN Job ON UserJob.JobId = Job.JobId
        JOIN Company ON Job.Company = Company.CompanyName
        LEFT JOIN JobLocation ON Job.JobId = JobLocation.JobIdFK
        WHERE UserJobId = %s
        """
    '''
    add_user_job

    adds a user job into the db

    args:
        user_id the UUID user_id
        job_id the id of the job as a str
    returns
        0 if no errors occured
    '''
    def add_user_job(user_id_uuid : UUID | str, job_id : str) -> Job:
        user_id : str = str(user_id_uuid)
        logging.info("ADDING USER JOB WITH USER ID " + user_id + " AND JOB ID OF " + job_id)
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query : str = UserJobTable.__get_add_user_job_query()
                #Hashing!!! ahhhh Scary!
                #Just ensures that we have a unique combo of userIds to jobIds, no duplicants
                #Client will check this as well for less eronious calls
                user_job_id : str = UserJobTable.generate_user_job_id(user_id, job_id)
                try:
                    cursor.execute(query, (user_job_id, user_id, job_id))
                except IntegrityError as e:
                    logging.error("USER JOB ALREADY IN DB")
                    raise e
                logging.info("USER JOB SUCCESSFULLY ADDED")
                conn.commit()
                read_query = UserJobTable.__get_read_specific_user_job_query_full_join()
                cursor.execute(read_query, (user_job_id,))
                added_row = cursor.fetchone()
        return Job.create_with_sql_row(added_row)
    '''
    delete_user_job

    deletes the user job from the db

    args:
        user_id the UUID user id
        job_id the string job id
    returns
        0 if no error occured
    '''
    def delete_user_job(user_id_uuid : UUID | str, job_id : str) -> int:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                user_id : str = str(user_id_uuid)
                query : str = UserJobTable.__get_delete_user_job_query()
                user_job_id : str = UserJobTable.generate_user_job_id(user_id, job_id)
                cursor.execute(query, (user_job_id,))

                affected_rows = cursor.rowcount

                if affected_rows == 0:
                    logging.info("No user job found with the specified ID.")
                    logging.info(f"user_job_id: {user_job_id}, user_id: {user_id}, job_id: {job_id}")
                else:
                    logging.info("USER JOB SUCCESSFULLY DELETED")
                conn.commit()
        return 0
    '''
    update_user_job

    updates the user job given the job_id and user_id

    args:
        job_id: id of the job
        user_id: id of the user
        update_dict: key (key which were updating): value (new value)
    returns:
        new userSpecificJobData
    '''
    def update_user_job(job_id: str, user_id_uuid: UUID, update_dict: Dict) -> UserSpecificJobData:
        user_job_id = UserJobTable.generate_user_job_id(str(user_id_uuid), job_id)
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserJobTable.__get_update_user_job_by_id(update_dict)
                cursor.execute(query, (*update_dict.values(), user_job_id))
                conn.commit()
                read_query = UserJobTable.__get_read_specific_user_job_query()
                cursor.execute(read_query, (user_job_id,))
                updated_row = cursor.fetchone()
        return UserSpecificJobData.create_with_sql_row(updated_row)
    '''
    get_user_job

    gets all user jobs from db

    args:
        user_id the UUID user id
    returns
        list of all jobs as job object
    '''
    def get_user_jobs(user_id_uuid: UUID | str) -> list[Job]:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                user_id : str = str(user_id_uuid)
                query : str = UserJobTable.__get_read_user_jobs_query()
                cursor.execute(query, (user_id,))
                results: list[Dict[str, RowItemType]] = cursor.fetchall()
                results_list : list[Job] = [Job.create_with_sql_row(row) for row in results]
        return results_list
    