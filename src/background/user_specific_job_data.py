#(c) 2024 Daniel DeMoney. All rights reserved.
from datetime import datetime
from typing import Dict
from mysql.connector.types import RowType, RowItemType

class UserSpecificJobData:
    '''
    UserSpecificJobData

    gives the user specific data to job instances. Basically a wrapper for UserJob.

    if a job has a userData of NONE it is a "pure" job representation IE only represents the job,
    not connected to any user

    attributes
        isFavorite: Bool
        hasApplied: Bool
        timeSelected: datetime
    '''
    def __init__(self, isFavorite: bool, hasApplied: bool, timeSelected: datetime):
        self.is_favorite = isFavorite
        self.has_applied = hasApplied
        self.time_selected = timeSelected
    def to_json(self) -> Dict:
        return {
            "isFavorite" : self.is_favorite,
            "hasApplied": self.has_applied,
            "timeSelected": int(self.time_selected.timestamp()) if self.time_selected is not None else None,
        }
    @classmethod
    def create_with_json(cls, json_object: Dict) -> 'UserSpecificJobData':
        return cls(json_object["isFavorite"], json_object["hasApplied"], json_object["timeSelected"])
    @classmethod
    def create_with_sql_row(cls, sql_query_row: (Dict[str, RowItemType])) -> 'UserSpecificJobData':
        return cls(sql_query_row["IsFavorite"] == 1, sql_query_row["HasApplied"] == 1, sql_query_row["TimeSelected"])
    
    