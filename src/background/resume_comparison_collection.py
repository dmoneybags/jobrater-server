#© 2024 Daniel DeMoney. All rights reserved.
import json
from pymongo import MongoClient
from pymongo.results import InsertOneResult, InsertManyResult
from database_functions import DatabaseFunctions
from job import Job
from typing import Dict
from uuid import UUID

class ResumeComparisonCollection:
    COLLECTION_NAME = "ResumeComparisons"
    def add_resume_comparison(resumeComparisonDict: Dict) -> InsertOneResult:
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            result: InsertOneResult = collection.insert_one(resumeComparisonDict)
        return result.inserted_id is not None
    def add_resume_comparisons(resumeComparisonDicts: list[Dict]) -> InsertManyResult:
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            results: InsertManyResult = collection.insert_many(resumeComparisonDicts)
        return results
    def read_user_resume_comparisons(userId: str | UUID) -> list[Dict]:
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            query = {"userId": str(userId)}
            results: list[Dict] = list(collection.find(query))
        return results
    def read_job_resume_comparisons(jobId: str, userId: str) -> list[Dict]:
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            query = {"jobId": jobId, "userId": str(userId)}
            results = list(collection.find(query))
        return results
    def read_specific_resume_comparison(jobId: str, resumeId: str) -> Dict:
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            query = {"jobId": jobId, "resumeId": str(resumeId)}
            result = collection.find_one(query)
        return result
    def delete_job_resume_comparisons(jobId: str, userId: str):
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            query = {"jobId": jobId, "userId": str(userId)}
            results_len: int = collection.delete_many(query)
        return results_len
    def delete_user_resume_comparisons(userId: str | UUID):
        with MongoClient(DatabaseFunctions.MONGODB_URL) as client:
            db = client[DatabaseFunctions.MONGODB_DB_NAME]
            collection = db[ResumeComparisonCollection.COLLECTION_NAME]
            query = {"userId": userId}
            results_len: int = collection.delete_many(query)
        return results_len
    def get_job_best_resume_comparison(jobId: str, userId: str | UUID):
        job_resume_comparisons = ResumeComparisonCollection.read_job_resume_comparisons(jobId, userId)
        best_resume_comparison = None
        for resume_comparison in job_resume_comparisons:
            if not best_resume_comparison or resume_comparison["matchScore"] > best_resume_comparison["matchScore"]:
                best_resume_comparison = resume_comparison
        return best_resume_comparison
    def get_best_resume_scores_object(jobs: list[Job], userId: str | UUID):
        best_resume_scores = {}
        for job in jobs:
            best_resume_comparison = ResumeComparisonCollection.get_job_best_resume_comparison(job.job_id, userId)
            best_resume_scores[job.job_id] = best_resume_comparison["matchScore"] if best_resume_comparison else None
        return best_resume_scores
