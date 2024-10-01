#(c) 2024 Daniel DeMoney. All rights reserved.
from uuid import UUID
from database_functions import DatabaseFunctions, get_connection
from location import Location
from typing import Dict
from mysql.connector.cursor import MySQLCursor
from mysql.connector.connection_cext import CMySQLConnection
from mysql.connector.errors import IntegrityError
from mysql.connector.types import RowType, RowItemType
import logging

class UserLocationTable:
    '''
    get_add_location_query

    gets the query to add a UserLocation

    returns:
        query str
    '''
    def __get_add_location_query(location_json : Dict) -> str:
        cols : list[str] = ["userIdFk"]
        cols.extend(list(location_json.keys()))
        col_str : str = ", ".join(cols)
        vals : str = ", ".join(["%s"] * len(cols))
        return f"""
        INSERT INTO UserLocation ({col_str}) VALUES ({vals})
        """
    '''
    get_read_location_query

    gets the query to read a JobLocation by the query str

    returns:
        query str
    '''
    def __get_read_location_query() -> str:
        return f"""
        SELECT * FROM USERLOCATION WHERE UserIdFk = %s
        """
    '''
    __get_update_user_location_query

    gets string query to update an instance

    args:
        location_update_data: json of either a full location object dumped out to json
        or just a dict of updated values
    returns:
        the query str with %s for injection
    '''
    def __get_update_user_location_query(location_update_data : Dict) -> str:
        logging.info(location_update_data)
        cols : list[str] = list(location_update_data.keys())
        col_str : str = "=%s, ".join(cols)
        #add on last replacement str
        col_str = col_str + "=%s"
        update_str : str = f"UPDATE USERLOCATION SET {col_str} WHERE USERLOCATION.UserIdFk = %s"
        return update_str
    def __get_delete_location_query() -> str:
        return f"""
        DELETE FROM USERLOCATION WHERE UserIdFk=%s
        """
    '''
    add_user_location

    Adds a users_location to database with a foreign key to User

    args:
        location: Location object that corresponds to user
        user_id: UUID object of the user
    returns:
        0
    '''
    def add_user_location(location: Location, user_id: UUID | str) -> int:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                logging.info("ADDING USER LOCATION")
                location_json : Dict = location.to_json()
                query = UserLocationTable.__get_add_location_query(location_json)
                #unpack values
                params = [str(user_id), *list(location_json.values())]
                try:
                    cursor.execute(query, params)
                    conn.commit()
                except IntegrityError:
                    logging.info("User location already in db")
        logging.info(f"ADDED USER LOCATION")
        return 0
    '''
    try_read_location

    attempts to read a users location from the db, returns none if not found

    args:
        user_id: UUID or Str of users id
    returns:
        location object or none
    '''
    def try_read_location(user_id : UUID | str) -> Location | None:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                logging.info("READING USER LOCATION OBJECT")
                query : str = UserLocationTable.__get_read_location_query()
                cursor.execute(query, (str(user_id),))
                result : (Dict[str, RowItemType]) = cursor.fetchone()
                if not result:
                    return None
        return Location.try_get_location_from_sql_row(result)
    '''
    update_location

    updates user location

    args:
        user_id: UUID or Str of users id
        update_dict: key col to val new value
    returns:
        new location
    '''
    def update_location(user_id : UUID | str, location_json: Dict) -> Location | None:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                logging.info("UPDATING USER LOCATION OBJECT")
                update_str : str = UserLocationTable.__get_update_user_location_query(location_json)
                #convert the values of our json to a list
                #Our list will retain order
                #No sql injection!
                #will have to check for lowered case strs too 
                if "UserIdFk" in location_json.values():
                    return 1
                params : list = list(location_json.values())
                params.append(str(user_id))
                #Execute the query
                logging.debug(update_str)
                logging.debug(params)
                cursor.execute(update_str, params)
                conn.commit()
        return UserLocationTable.try_read_location(user_id)
         

    '''
    delete_location

    deletes user location

    args:
        user_id: UUID or Str of users id
    returns:
        0
    '''
    def delete_location(user_id : UUID | str) -> int:
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                logging.info("DELETING USER LOCATION OBJECT")
                query : str = UserLocationTable.__get_delete_location_query()
                cursor.execute(query, (str(user_id),))
        return 0