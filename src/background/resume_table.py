#(c) 2024 Daniel DeMoney. All rights reserved.
from database_functions import DatabaseFunctions, get_connection
from typing import Dict
from uuid import UUID
from resume import Resume
from mysql.connector.cursor import MySQLCursor
from mysql.connector.connection_cext import CMySQLConnection
from mysql.connector.types import RowType, RowItemType
import datetime
import logging

class ResumeTable:
    '''
    __get_add_resume_query

    Holds query to add resume
    '''
    def __get_add_resume_query() -> str:
        return """
            INSERT INTO Resumes (UserId, Name, FileName, FileType, FileContent, FileText, IsDefault) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
    '''
    __get_delete_resume_query

    Holds query to delete resume
    '''
    def __get_delete_resume_query() -> str:
        return """
            DELETE FROM Resumes WHERE Id = %s
        """
    '''
    __get_read_resumes_query

    query to get all a users resumes
    '''
    def __get_read_resumes_query() -> str:
        return """
            SELECT * FROM RESUMES WHERE UserId = %s
        """
    def __get_read_resume_by_id() -> str:
        return """
            SELECT * FROM RESUMES WHERE Id = %s
        """
    def __get_update_resume_by_id(update_dict: Dict) -> str:
        col_str: str = ', '.join([f"{col_name} = %s" for col_name in update_dict.keys()])
        return f"""
            UPDATE RESUMES 
            SET {col_str}
            WHERE Id = %s
        """
    def __get_clear_defaults() -> str:
        return f"""
            UPDATE RESUMES
            SET isDefault = 0
            WHERE UserId = %s
        """
    '''
    add_resume

    adds a resume to the db

    user_id: uuid of the user
    resume: Resume object we are adding
    '''
    def add_resume(user_id: UUID | str, resume: Resume) -> int:
        user_id : str = str(user_id)
        logging.info("ADDING RESUME WITH USER ID " + user_id + " FILENAME OF " + resume.file_name)
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query : str = ResumeTable.__get_add_resume_query()
                resume_json: Dict = resume.to_sql_friendly_json()
                resume_values: list = [
                    user_id,
                    resume_json["name"],
                    resume_json["fileName"],
                    resume_json["fileType"],
                    resume_json["fileContent"],
                    resume_json["fileText"],
                    resume_json["isDefault"]
                    ]
                try:
                    cursor.execute(query, resume_values)
                except Exception as e:
                    logging.error("RECIEVED ERROR WHEN ATTEMPTING TO ADD RESUME")
                    logging.error(e)
                    cursor.close()
                    conn.close()
                    raise e
                logging.info("RESUME SUCCESSFULLY ADDED")
                conn.commit()
                resume.upload_date = datetime.datetime.utcnow()
                resume.id = cursor.lastrowid
                logging.info("Resume uploaded at ")
                logging.info(resume.upload_date) 
                resume_json = resume.to_json()
                logging.info(resume_json["uploadDate"])
        return resume_json
    '''
    delete_resume

    deletes a resume from our db

    resume_id: id of the resume we are deleting
    '''
    def delete_resume(resume_id: int) -> int:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query : str = ResumeTable.__get_delete_resume_query()
                cursor.execute(query, (resume_id,))
                logging.info("RESUME SUCCESSFULLY DELETED")
                conn.commit()
        return 0
    '''
    read_user_resumes

    returns all resumes assoiciated with a user

    user_id: uuid or str uuid of user

    returns: list of resumes 
    '''
    def read_user_resumes(user_id: UUID | str) -> list[Resume]:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                user_id : str = str(user_id)
                query: str = ResumeTable.__get_read_resumes_query()
                cursor.execute(query, (user_id,))
                results: list[Dict[str, RowItemType]] = cursor.fetchall()
                results_list : list[Resume] = [Resume.create_with_sql_row(row) for row in results]
        return results_list
    '''
    read_resume_by_id

    reads resume by it's specific id

    resume_id: the id of the resume we are reading

    returns:

    resume we read
    '''
    def read_resume_by_id(resume_id: int) -> Resume:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query: str = ResumeTable.__get_read_resume_by_id()
                cursor.execute(query, (resume_id,))
                result: Dict[str, RowItemType] = cursor.fetchone()
        return Resume.create_with_sql_row(result)
    '''
    update_resume_by_id

    updates a resume by its id

    update_dict: col_name to update -> new value of the column

    returns: updated resume
    '''
    def update_resume_by_id(resume_id: int, user_id: str, update_dict: Dict) -> Resume:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                if "isDefault" in update_dict:
                    clear_default_query = ResumeTable.__get_clear_defaults()
                    cursor.execute(clear_default_query, (str(user_id),))
                query: str = ResumeTable.__get_update_resume_by_id(update_dict)
                cursor.execute(query, (*update_dict.values(), resume_id))
                conn.commit()
        return ResumeTable.read_resume_by_id(resume_id)
