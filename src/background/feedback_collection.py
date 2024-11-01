#(c) 2024 Daniel DeMoney. All rights reserved.
from database_functions import DatabaseFunctions
from pymongo import MongoClient
from pymongo.results import InsertOneResult, InsertManyResult
from typing import Dict

class FeedbackCollection:
    COLLECTION_NAME = "Feedback"
    def add_feedback(resumeComparisonDict: Dict) -> InsertOneResult:
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[FeedbackCollection.COLLECTION_NAME]
            result: InsertOneResult = collection.insert_one(resumeComparisonDict)
        return result.inserted_id is not None