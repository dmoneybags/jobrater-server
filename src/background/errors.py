#(c) 2024 Daniel DeMoney. All rights reserved.
class DuplicateUserJob(Exception):
    """when a user tries to add the same job twice"""
    
    def __init__(self, message="Error, user has already added this job"):
        self.message = message
        
    def __str__(self):
        return self.message

class NoFreeRatingsLeft(Exception):
    """when a user attempts to use a resume rating when they have ran out of free ones"""
    
    def __init__(self, message="Error, user has already used all free resume ratings"):
        self.message = message
        
    def __str__(self):
        return self.message