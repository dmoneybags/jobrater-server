import datetime
from datetime import timedelta
from typing import Dict
from errors import NoFreeRatingsLeft
from database_functions import DatabaseFunctions, get_connection
from user_table import UserTable
import logging

class UserFreeDataTable:
    def __get_add_free_data_query() -> str:
        return 'INSERT INTO UserFreeData (UserIdFk, Email) VALUES (%s, %s)'
    def __get_read_free_data_query() -> str:
        return 'SELECT * FROM UserFreeData WHERE UserIdFk=%s'
    def __get_update_free_data_query() -> str:
        return 'UPDATE UserFreeData SET FreeRatingsLeft=%s, LastReload=%s WHERE UserIdFk=%s'
    def __get_read_by_email_query() -> str:
        return 'SELECT * FROM UserFreeData WHERE Email=%s'
    def __get_reassign_free_data_query() -> str:
        return 'UPDATE UserFreeData SET UserIdFk=%s WHERE Email=%s'
    #IMPORTANT, this only returns the explicit data in the db, and does not reload, use get_free_resume data for any client facing info
    def read_free_data(userId: str) -> Dict:
        userId = str(userId) #Sanity check no uuids
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserFreeDataTable.__get_read_free_data_query()
                cursor.execute(query, (userId,))
                result = cursor.fetchone()
        return result
    def read_free_data_by_email(email: str) -> str:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserFreeDataTable.__get_read_by_email_query()
                cursor.execute(query, (email,))
                result = cursor.fetchone()
        return result
    def update_free_data(userId: str, free_ratings_left: int, last_reload: datetime.datetime) -> int:
        userId = str(userId) #Sanity check no uuids
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserFreeDataTable.__get_update_free_data_query()
                cursor.execute(query, (free_ratings_left, last_reload, userId,))
                conn.commit()
        return 0
    def add_free_data(userId: str):
        userId = str(userId) #Sanity check no uuids
        user = UserTable.read_user_by_id(userId)
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserFreeDataTable.__get_add_free_data_query()
                cursor.execute(query, (userId, user.email))
                conn.commit()
    def reassign_free_data(userId: str, email: str):
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserFreeDataTable.__get_reassign_free_data_query()
                cursor.execute(query, (userId, email))
                conn.commit()
    def use_free_resume_rating(userId: str):
        userId = str(userId) #Sanity check no uuids
        free_data = UserFreeDataTable.read_free_data(userId)
        #Add if for any reason its not in there
        if not free_data:
            logging.critical(f"COULD NOT FIND USER FREE DATA FOR USERID: {userId}")
            raise NoFreeRatingsLeft()
        if datetime.datetime.now() - free_data["CreatedAt"] > timedelta(days=14):
            raise NoFreeRatingsLeft()
        #if we have a non zero number of ratings left
        if free_data["FreeRatingsLeft"]:
            #decrement
            free_data["FreeRatingsLeft"] = free_data["FreeRatingsLeft"] - 1
            UserFreeDataTable.update_free_data(userId, free_data["FreeRatingsLeft"], free_data["LastReload"])
            return
        if datetime.datetime.now() - free_data["LastReload"] > timedelta(days=1):
            free_data["LastReload"] = datetime.datetime.now()
            #2 because we're using one here
            free_data["FreeRatingsLeft"] = 2
            UserFreeDataTable.update_free_data(userId, free_data["FreeRatingsLeft"], free_data["LastReload"])
            return
        raise NoFreeRatingsLeft()
    def get_free_resume_info(userId: str) -> Dict:
        free_data: Dict = UserFreeDataTable.read_free_data(userId)
        if datetime.datetime.now() - free_data["LastReload"] > timedelta(days=1):
            free_data["LastReload"] = datetime.datetime.now()
            free_data["FreeRatingsLeft"] = 3
            UserFreeDataTable.update_free_data(userId, free_data["FreeRatingsLeft"], free_data["LastReload"])
            return UserFreeDataTable.read_free_data(userId)
        return free_data
    def is_discountable(user_id: str) -> bool:
        user_free_data: Dict = UserFreeDataTable.read_free_data(user_id)
        
        created_at: datetime = user_free_data["CreatedAt"]

        one_week_ago = datetime.datetime.now() - timedelta(days=7)

        return created_at >= one_week_ago