#© 2024 Daniel DeMoney. All rights reserved.
from typing import Dict
from uuid import UUID
from database_functions import DatabaseFunctions, get_connection
from mysql.connector.cursor import MySQLCursor
from mysql.connector.connection_cext import CMySQLConnection
from mysql.connector.errors import IntegrityError
from user_preferences import UserPreferences
from job import Job

class UserPreferencesTable:
    '''
    __get_add_user_preferences_query

    gets the query to add an instance into the db

    args:
        None
    returns:
        string query
    '''
    def __get_add_user_preferences_query() -> str:
        return """
            INSERT INTO UserPreferences (UserIdFk, DesiredPay, DesiredPaymentFreq, DesiredCommute, DesiresRemote,
            DesiresHybrid, DesiresOnsite, DesiredCareerStage, AutoActiveOnNewJobLoaded, AutoCompareResumeOnNewJobLoaded, SaveEveryJobByDefault) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
    '''
    __get_read_user_preferences_query

    gets the query to read an instance from the db

    args:
        None
    returns:
        string query
    '''
    def __get_read_user_preferences_query() -> str:
        return """
            SELECT * FROM UserPreferences WHERE UserIdFk = %s
        """
    '''
    __get_update_user_preferences_query

    gets string query to update an instance

    args:
        preferences_update_data: json of either a full preferences object dumped out to json
        or just a dict of updated values
    returns:
        the query str with %s for injection
    '''
    def __get_update_user_preferences_query(preferences_update_data : Dict) -> str:
        print(preferences_update_data)
        cols : list[str] = list(preferences_update_data.keys())
        col_str : str = "=%s, ".join(cols)
        #add on last replacement str
        col_str = col_str + "=%s"
        update_str : str = f"UPDATE UserPreferences SET {col_str} WHERE UserPreferences.UserIdFk = %s"
        return update_str
    '''
    add_user_preferences

    adds a user preferences instance to the db

    args:
        preferences UserPreferences
    returns
        0 if no errors occured
    '''
    def add_user_preferences(preferences: UserPreferences) -> int:
        print("ADDING USER PREFERENCES WITH USER ID " + str(preferences.user_id))
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query : str = UserPreferencesTable.__get_add_user_preferences_query()
                try:
                    cursor.execute(query, (str(preferences.user_id), 
                                        preferences.desired_pay, 
                                        Job.payment_frequency_to_str(preferences.desired_payment_freq),
                                        preferences.desired_commute, 
                                        preferences.desires_remote, 
                                        preferences.desires_hybrid,
                                        preferences.desires_onsite, 
                                        preferences.desired_career_stage,
                                        preferences.auto_activate_on_new_job_loaded, 
                                        preferences.auto_compare_resume_on_new_job_loaded, 
                                        preferences.save_every_job_by_default))
                except IntegrityError as e:
                    print("USER PREFERENCES ALREADY IN DB")
                    raise e
                print("USER PREFERENCES SUCCESSFULLY ADDED")
                conn.commit()
        return 0
    def read_user_preferences(user_id: UUID | str):
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query: str = UserPreferencesTable.__get_read_user_preferences_query()
                cursor.execute(query, (str(user_id),))
                preferences_dict = cursor.fetchone()
        return UserPreferences.create_from_sql_query_row(preferences_dict)
    '''
    update_user_preferences

    updates user preferences instance

    args:
        preferences_json: json of {col: value} to update
    returns:
        0 if no errors occured
    '''
    def update_user_preferences(preferences_json: Dict, user_id: UUID | str) -> int:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                update_str : str = UserPreferencesTable.__get_update_user_preferences_query(preferences_json)
                #convert the values of our json to a list
                #Our list will retain order
                #No sql injection!
                #will have to check for lowered case strs too 
                if "UserIdFk" in preferences_json.values():
                    return 1
                params : list = list(preferences_json.values())
                params.append(str(user_id))
                #Execute the query
                print(update_str)
                print(params)
                cursor.execute(update_str, params)
                conn.commit()
        #return success
        return UserPreferencesTable.read_user_preferences(user_id)
    
