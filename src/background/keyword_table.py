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
