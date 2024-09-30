#© 2024 Daniel DeMoney. All rights reserved.
'''
TO DO: 
*CRUD methods for company CHECK
*change our query for adding the job to be created programatically with a
    "Get job values" function and then a "generate job query" function
    All our querys should be generated this way CHECK
*Change the glassdoor calls to check if the company is already in our db CHECK

'''

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
Through routines in

database_functions.py

TO DO:

make sure that when we check if the company exists all the values arent null
'''
#TO DO, we should not just leave cursor open

from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling, Error
from mysql.connector.connection_cext import CMySQLConnection
from mysql.connector.cursor import MySQLCursor
import json
import os
import uuid
from decimal import Decimal

class DatabaseFunctions:
    IS_PRODUCTION = os.getenv("ENVIRONMENT") == "production"
    print("VALUE FOR ISPRODUCTION:")
    print(IS_PRODUCTION)
    # Set database parameters based on the environment
    if IS_PRODUCTION:
        HOST = "ip-172-31-11-79.us-west-1.compute.internal"
        MYSQLUSER = os.getenv("SQLUSER") 
        MYSQLPASSWORD = os.getenv("SQLPASSWORD")
        DATABASE = "JOBDB"
        MONGODB_URL = "ip-172-31-3-247.us-west-1.compute.internal"
    else:
        HOST = "localhost"
        MYSQLUSER = "root"
        MYSQLPASSWORD = os.getenv("SQLPASSWORD")
        DATABASE = "JOBDB"
        MONGODB_URL = "mongodb://localhost:27017"
    DATABASE = "JOBDB"
    MONGODB_DB_NAME = "Jobrater"
    pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=10,  # Adjust pool size as needed
        host=HOST,
        user=MYSQLUSER,
        password=MYSQLPASSWORD,
        database=DATABASE
    )

    def get_connection() -> CMySQLConnection:
        conn = None
        try:
            conn = DatabaseFunctions.pool.get_connection()
            # Check if the connection is still valid
            if conn.is_connected():
                try:
                    cursor : MySQLCursor = conn.cursor()
                    cursor.execute("SELECT 1")  # Simple query to validate the connection
                    _ = cursor.fetchone()
                    cursor.close()
                except mysql.connector.Error as query_err:
                    # If the query fails, close and try to reconnect
                    print(f"Error with validation query: {query_err}")
                    conn.close()  # Close invalid connection
                    conn = DatabaseFunctions.pool.get_connection()  # Get a new connection
            else:
                # If the connection isn't valid, close and reconnect
                conn.close()
                conn = DatabaseFunctions.pool.get_connection()
                
        except mysql.connector.errors.OperationalError as e:
            print("Got operational error getting connection of:")
            print(e)
            # Handle case where reconnection is needed
            if conn:
                conn.reconnect(attempts=3, delay=5)  # Try to reconnect manually
            else:
                conn = DatabaseFunctions.pool.get_connection()  # If no conn, get one from pool
            
        except mysql.connector.Error as err:
            # Log and handle other errors
            print(f"Error: {err}")
            if conn:
                conn.close()
            raise err
        
        return conn

@contextmanager
def get_connection():
    print("Getting connection")
    conn = DatabaseFunctions.get_connection()
    try:
        yield conn
    finally:
        conn.close()
