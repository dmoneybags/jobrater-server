class DuplicateUserJob(Exception):
    """when a user tries to add the same job twice"""
    
    def __init__(self, message="Error, user has already added this job"):
        self.message = message
        
    def __str__(self):
        return self.message