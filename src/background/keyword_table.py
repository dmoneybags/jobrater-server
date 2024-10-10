import logging
from database_functions import DatabaseFunctions, get_connection
from uuid import UUID

NUMKEYWORDS = 10

#no read method necessary, we left join it when we read the user
#keywords are held in the user preferences object
class KeywordTable:
    def __get_add_keywords_query() -> str:
        return ''' 
            INSERT INTO KeywordList (UserIdFk, PositiveKeyword1, PositiveKeyword2, PositiveKeyword3, PositiveKeyword4, PositiveKeyword5,
            PositiveKeyword6, PositiveKeyword7, PositiveKeyword8, PositiveKeyword9, PositiveKeyword10, NegativeKeyword1, NegativeKeyword2,
            NegativeKeyword3, NegativeKeyword4, NegativeKeyword5, NegativeKeyword6, NegativeKeyword7, NegativeKeyword8, NegativeKeyword9,
            NegativeKeyword10) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
    def __get_update_keywords_query() -> str:
        return '''
            UPDATE KeywordList
            SET PositiveKeyword1 = %s, PositiveKeyword2 = %s, PositiveKeyword3 = %s, PositiveKeyword4 = %s, PositiveKeyword5 = %s,
            PositiveKeyword6 = %s, PositiveKeyword7 = %s, PositiveKeyword8 = %s, PositiveKeyword9 = %s, PositiveKeyword10 = %s, NegativeKeyword1 = %s, NegativeKeyword2 = %s,
            NegativeKeyword3 = %s, NegativeKeyword4 = %s, NegativeKeyword5 = %s, NegativeKeyword6 = %s, NegativeKeyword7 = %s, NegativeKeyword8 = %s, NegativeKeyword9 = %s,
            NegativeKeyword10 = %s
            WHERE UserIdFk= %s;
        '''
    def add_keywords(userId: UUID | str, positive_keywords: list[str], negative_keywords: list[str]) -> int:
        logging.info("ADDING USER KEYWORDS WITH USER ID " + str(userId))
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                #Make sure we fill any holes with nones
                positive_keywords.extend([None] * (NUMKEYWORDS - len(positive_keywords)))
                #Sanity check that its 10 at the longest (or whatever num keywords is)
                positive_keywords = positive_keywords[:NUMKEYWORDS]
                negative_keywords.extend([None] * (NUMKEYWORDS - len(negative_keywords)))
                negative_keywords = negative_keywords[:NUMKEYWORDS]
                query = KeywordTable.__get_add_keywords_query()
                cursor.execute(query, (userId, *positive_keywords, *negative_keywords))
                logging.info("USER KEYWORDS SUCCESSFULLY ADDED")
                conn.commit()
        return 0
    def update_keywords(userId: UUID | str, positive_keywords: list[str], negative_keywords: list[str]) -> int:
        logging.info("UPDATING USER KEYWORDS WITH USER ID " + str(userId))
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                #Make sure we fill any holes with nones
                positive_keywords.extend([None] * (NUMKEYWORDS - len(positive_keywords)))
                #Sanity check that its 10 at the longest (or whatever num keywords is)
                positive_keywords = positive_keywords[:NUMKEYWORDS]
                negative_keywords.extend([None] * (NUMKEYWORDS - len(negative_keywords)))
                negative_keywords = negative_keywords[:NUMKEYWORDS]
                query = KeywordTable.__get_update_keywords_query()
                cursor.execute(query, (*positive_keywords, *negative_keywords, userId))
                logging.info("USER KEYWORDS SUCCESSFULLY UPDATED")
                conn.commit()
        return 0