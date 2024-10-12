from database_functions import DatabaseFunctions, get_connection
from mysql.connector.cursor import MySQLCursor
from mysql.connector.connection_cext import CMySQLConnection
from mysql.connector.types import RowType, RowItemType

class EmailConfirmationTable:
    '''
    __get_new_confirmation_code_query

    Gets the query to add a new confirmation code.

    If one isn't already in the db we add a new row. If it is we update the row with the new code.
    '''
    def __get_new_confirmation_code_query():
        return '''
            INSERT INTO EmailConfirmation (Email, ConfirmationCode)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE 
                ConfirmationCode = VALUES(ConfirmationCode)'''
    def __get_read_confirmation_code_query():
        return '''
            SELECT ConfirmationCode, CreatedAt FROM EmailConfirmation
            WHERE Email = %s
        '''
    def add_confirmation_code(email, confirmation_code):
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = EmailConfirmationTable.__get_new_confirmation_code_query()
                values = (email, confirmation_code)
                cursor.execute(query, values)
                conn.commit()
        return 0
    def readConfirmationCode(email):
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = EmailConfirmationTable.__get_read_confirmation_code_query()
                cursor.execute(query, (email,))
                result = cursor.fetchone()
                if not result:
                    return None
                return result
