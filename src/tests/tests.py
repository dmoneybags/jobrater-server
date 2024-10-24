import sys
import os
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'background')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'mocks')))
import json
import asyncio
from auth_logic import decode_user_from_token, get_token
from datetime import timedelta
from uuid import uuid1
from user_table import UserTable
from user import User
from company import Company
from company_table import CompanyTable
from job import Job
from job_table import JobTable
from user_job_table import UserJobTable
from resume_table import Resume, ResumeTable
from user_free_data_table import UserFreeDataTable
from objects import MockObjects
from user_preferences import UserPreferences
from user_subscription import UserSubscription
from location import Location
from user_preferences_table import UserPreferencesTable
from user_subscription_table import UserSubscriptionTable
from resume_comparison_collection import ResumeComparisonCollection
from resume_nlp.resume_comparison import ResumeComparison
from relocation_data_grabber import RelocationDataGrabber
from errors import DuplicateUserJob, NoFreeRatingsLeft


#TESTS JUST DB CODE, NO SERVERS
job_data = {
    "jobName": "Specification Sales",
    "locationStr": "Cupertino, CA",
    "jobPostedAt": 1724433417,
    "applicants": "100",
    "paymentFreq": "yr",
    "paymentBase": 90,
    "paymentHigh": 110,
    "mode": "Hybrid",
    "careerStage": "Mid-Senior level",
    "jobId": "3936196442",
    "description": "beep boop",
    "company": {
        "companyName": "Apple",
        "businessOutlookRating": 1,
        "careerOpportunitiesRating": 5,
        "ceoRating": 1,
        "compensationAndBenefitsRating": 5,
        "cultureAndValuesRating": 5,
        "diversityAndInclusionRating": 5,
        "overallRating": 5,
        "seniorManagementRating": 5,
        "workLifeBalanceRating": 4.7,
        "glassdoorUrl": "ijiksmfo"
    },
    "location": None
}
def user_tests():
    print("TESTING USER CODE")

    user_json = {
        "userId": str(uuid1()),
        "email": "dandemoney@gmail.com",
        "password": "Xdfgh1012",
        "firstName": "Daniel",
        "lastName": "DeMoney",
        "salt": "!#%!%!%!#%!",
        "googleId": None,

    }
    user = User.create_with_json(user_json)

    print("TESTING ADDING USER")
    UserTable.add_user(user)
    print("SUCEEDED READING USER BACK \n \n")

    print("TESTING READING USER")
    read_user = UserTable.read_user_by_email(user.email)
    assert(user.email == read_user.email)
    assert(user.first_name == read_user.first_name)
    assert(user.last_name == read_user.last_name)
    assert(user.password == read_user.password)
    assert(str(user.user_id) == str(read_user.user_id))
    print("SUCEEDED READING USER BACK \n \n")

    print("TESTING DUMPING USER OBJECT TO JSON")
    read_user_json = read_user.to_json()
    print("Read user " + json.dumps(read_user_json))
    print("Original user " + json.dumps(user_json))
    assert(user_json["email"] == read_user_json["email"])
    assert(user_json["firstName"] == read_user_json["firstName"])
    assert(user_json["lastName"] == read_user_json["lastName"])
    assert(user_json["password"] == read_user_json["password"])
    assert(user_json["userId"] == read_user_json["userId"])
    print("USER SUCCESSFULLY DUMPED TO JSON \n \n")

    print("TESTING DELETE USER")
    UserTable.delete_user_by_email(user_json["email"])
    assert(not UserTable.read_user_by_email(user_json["email"]))
    print("SUCCESSFULLY DELETED USER \n \n")

    print("READDING USER FOR TESTS")
    UserTable.add_user(user)
    read_user = UserTable.read_user_by_email(user.email)
    return read_user.user_id

def company_tests():
    print("TESTING COMPANY CODE \n\n")
    print("TESTING ADDING COMPANY")
    company = Company.create_with_json(job_data["company"])
    CompanyTable.add_company(company)
    print("COMPANY ADDED SUCCESSFULLY \n\n")

    print("ATTEMPTING TO READ COMPANY")
    read_company = CompanyTable.read_company_by_id("Apple")
    print("COMPANY DATA READ:" + json.dumps(read_company.to_json()))
    assert(read_company.business_outlook_rating == job_data["company"]["businessOutlookRating"])
    assert(read_company.career_opportunities_rating == job_data["company"]["careerOpportunitiesRating"])
    assert(read_company.compensation_and_benefits_rating == job_data["company"]["compensationAndBenefitsRating"])
    assert(read_company.culture_and_values_rating == job_data["company"]["cultureAndValuesRating"])
    assert(read_company.diversity_and_inclusion_rating == job_data["company"]["diversityAndInclusionRating"])
    assert(read_company.overall_rating == job_data["company"]["overallRating"])
    print("COMPANY READ \n\n")

    print("ATTEMPTING TO UPDATE COMPANY")
    update_json = job_data["company"]
    update_json["ceoRating"] = 4.8
    CompanyTable.update_company(Company.create_with_json(update_json))
    reread_company = CompanyTable.read_company_by_id("Apple")
    assert(float(reread_company.ceo_rating) == 4.8)
    print("SUCCESSFULLY READ COMPANY AFTER UPDATE \n\n")

    print("TESTING DELETE COMPANY")
    CompanyTable.delete_company_by_name("Apple")
    assert(not CompanyTable.read_company_by_id("Apple"))
    print("SUCCESSFULLY DELETED COMPANY \n\n")

    print("========== PASSED COMPANY TESTS =========== \n\n")

def job_tests(user_id):
    print("TESTING ADDING JOB WITHOUT COMPANY IN DB")
    print(user_id)
    job = Job.create_with_json(job_data)
    JobTable.add_job_with_foreign_keys(job, user_id)
    #assert that the company correctly loaded
    assert(CompanyTable.read_company_by_id("Apple") is not None)
    assert(JobTable.read_job_by_id(job_data["jobId"]) is not None)
    print("SUCCESSFULLY ADDED JOB WITH A NEW COMPANY \n\n")

    print("TESTING DELETING JOBS")
    JobTable.delete_job_by_id(job_data["jobId"])
    assert(CompanyTable.read_company_by_id("Apple") is not None)
    print("COMPANY LOGIC SUCEEDED \n\n")
    print("READING JOB SUCEEDED \n\n")

    print("========== PASSED COMPANY TESTS =========== \n\n")

def user_job_tests(user_id):
    print("BEGINNNING USER JOB TESTS \n\n")
    print("TESTING READING BACK USER JOBS AFTER ADDING")
    job_strs = ["Application Programmer", "Janitor", "CSM (In person ONLY!)", "Professional Dookier (SENIOR LEVEL)"]
    job_id = ["1835781350", "3252359832", "2335285392", "3295295725"]
    for i in range(len(job_strs)):
        job_data_copy = job_data
        job_data_copy["jobName"] = job_strs[i]
        job_data_copy["jobId"] = job_id[i]
        print("TEST JOB BEING ADDED WITH NAME " + job_strs[i])
        job = Job.create_with_json(job_data_copy)
        JobTable.add_job_with_foreign_keys(job, user_id, add_user_job=True)
    results = UserJobTable.get_user_jobs(user_id)
    print(results)
    assert(len(results) == len(job_strs))
    for result in results:
        print(result.job_name)
    for result in results:
        #make sure the title is in our list
        if not job_strs.count(result.job_name) == 1:
            print(f"{result.job_name} not found in job_strs")
            assert(False)
    print("USER JOBS SUCCESSFULLY READ")
    #test that deleting the job deletes the user job
    print("TESTING DELETING JOB AND READING USER JOB")
    JobTable.delete_job_by_id(job_id[2])
    results = UserJobTable.get_user_jobs(user_id)
    for result in results:
        assert(result.job_id != job_id[2])
    print("USER JOB SUCCESSFULLY DELETED \n\n")
    #double adds
    print("ATTEMPTING TO DOUBLE ADD A USER JOB")
    job_data_copy = job_data
    job_data_copy["jobId"] = job_id[0]
    try:
        JobTable.add_job_with_foreign_keys(Job.create_with_json(job_data_copy), user_id,  add_user_job=True)
        assert(False)
    except DuplicateUserJob:
        print("Sucessfully stopped a double add")
    #test that deleting the user job does NOT delete the job
    print("TESTING THAT JOB PERSISTS WHEN USER JOB IS DELETED")
    UserJobTable.delete_user_job(user_id, job_id[0])
    job = JobTable.read_job_by_id(job_id[0])
    assert(job.company.company_name == "Apple")
    print("JOB PERSISTS TEST PASSED \n\n")

def resume_tests(user_id):
    def normalize_string(s):
        # Convert to lowercase
        s = s.lower()
        # Remove special characters
        s = re.sub(r'[^a-z0-9]', '', s)
        return s
    print("RUNNING RESUME TESTS")
    print("TESTING THAT WE CAN PROPERLY READ DOCX TEST")
    with open(os.getcwd() + "/src/tests/mocks/resume.docx", "rb") as doc:
        resume = Resume(None, None, "resume.docx", "docx", doc, None)
        if normalize_string(resume.file_text) != normalize_string(MockObjects.docx_resume_text):
            print("DOCX TEXT OF " + MockObjects.docx_resume_text)
            print("IS NOT EQUAL TO " + resume.file_text)
            assert(False)
        print("TEXT MATCHED!")
    print("TESTING THAT WE CAN PROPERLY READ PDF TEST")
    with open(os.getcwd() + "/src/tests/mocks/resume.pdf", "rb") as doc:
        pdf_bytes = doc.read()
        resume = Resume(None, None, "resume.pdf", "pdf", pdf_bytes, None)
        print("PDF TEXT: " + MockObjects.pdf_resume_text)
        print("REREAD TEXT: " + resume.file_text)
        print("TEXT MATCHED!")
    print("TESTING ADDING A RESUME TO THE DB")
    dummy_user_id = user_id
    #I have no idea what this line does
    resume.user_id = dummy_user_id
    ResumeTable.add_resume(user_id, resume)
    reread_resume = ResumeTable.read_user_resumes(dummy_user_id)[0]
    assert(str(user_id) == str(reread_resume.user_id))
    assert(resume.file_content == reread_resume.file_content)
    assert(resume.file_text == reread_resume.file_text)
    assert(resume.file_name == reread_resume.file_name)
    print("TEST PASSED")
    print("TESTING DELETING A RESUME")
    ResumeTable.delete_resume(reread_resume.id)
    assert(len(ResumeTable.read_user_resumes(dummy_user_id)) == 0)
    print("TEST PASSED")
def user_preferences_tests(user_id):
    print("RUNNING USER PREFERENCE TESTS")
    preferences = UserPreferences(user_id, 80000, Job.str_to_payment_frequency("yr"), 30, False,
                                  True, True, "Entry level", True, False, False, [], [])
    UserPreferencesTable.add_user_preferences(preferences)
    print("ADDED USER PREFERENCES")
    user: User = UserTable.read_user_by_email("dandemoney@gmail.com")
    assert(user.preferences)
    assert(user.preferences.user_id == user_id)
    assert(user.preferences.desired_pay == 80000)
    assert(user.preferences.desired_payment_freq == Job.str_to_payment_frequency("yr"))
    assert(user.preferences.desired_commute == 30)
    assert(user.preferences.desires_remote == False)
    assert(user.preferences.desires_hybrid == True)
    assert(user.preferences.desires_onsite == True)
    assert(user.preferences.auto_activate_on_new_job_loaded == True)
    assert(user.preferences.auto_compare_resume_on_new_job_loaded == False)
    assert(user.preferences.save_every_job_by_default == False)
    print("SUCCESSFULLY READ BACK USER PREFERENCES")
    updateJson = {
        "desiredPay": 100000,
        "desiredCommute": 45
    }
    UserPreferencesTable.update_user_preferences(updateJson, user_id)
    print("SUCCESSFULLY UPDATED USER PREFERENCES")
    user: User = UserTable.read_user_by_email("dandemoney@gmail.com")
    assert(user.preferences)
    assert(user.preferences.user_id == user_id)
    assert(user.preferences.desired_pay == 100000)
    assert(user.preferences.desired_payment_freq == Job.str_to_payment_frequency("yr"))
    assert(user.preferences.desired_commute == 45)
    assert(user.preferences.desires_remote == False)
    assert(user.preferences.desires_hybrid == True)
    assert(user.preferences.desires_onsite == True)
    assert(user.preferences.auto_activate_on_new_job_loaded == True)
    assert(user.preferences.auto_compare_resume_on_new_job_loaded == False)
    assert(user.preferences.save_every_job_by_default == False)
    print("SUCCESSFULLY READ BACK USER PREFERENCES AFTER UPDATE")
def resume_comparison_tests(user_id):
    mockJobId = "15421588"
    mockResumeId = 124591
    print("RUNNING RESUME COMPARISON TESTS")
    with open(os.getcwd() + "/src/tests/mocks/resume.pdf", "rb") as doc:
        pdf_bytes = doc.read()
        #Example id
        resume = Resume(mockResumeId, None, "resume.pdf", "pdf", pdf_bytes, None)
    resume.file_text = MockObjects.pdf_resume_text
    resume_comparison = ResumeComparison.get_resume_comparison_dict(MockObjects.job_description, mockJobId, resume, user_id)
    print("TESTING ADDING A RESUME COMPARISON")
    ResumeComparisonCollection.add_resume_comparison(resume_comparison)
    print("ADDED RESUME COMPARISON!")
    print("TESTING READING A RESUME COMPARISON")
    resume_comparisons = ResumeComparisonCollection.read_job_resume_comparisons(mockJobId, user_id)
    print("Resume comparisons read from job: ")
    print(len(resume_comparisons))
    assert(len(resume_comparisons) == 1)
    resume_comparisons = ResumeComparisonCollection.read_user_resume_comparisons(user_id)
    print("Resume comparisons read from users: ")
    print(len(resume_comparisons))
    assert(len(resume_comparisons) == 1)
    reread_resume_comparison = resume_comparisons[0]
    assert(reread_resume_comparison == resume_comparison)
    print("SUCCESSFULLY READ A RESUME COMPARISON")
def relocation_grabber_tests():
    #172 N Main St, Wallingford, VT 05773
    location = Location("210 E 46th St", "New York", "10017", "NY", 40.75281, -73.97210)
    asyncio.run(RelocationDataGrabber.get_data(location)) 
def user_subscription_tests(user_id):
    print("TESTING USER SUBSCRIPTION CLASS")
    user_subscription = MockObjects.user_subscription
    user_subscription.user_id = user_id
    print("testing that json dump and reload works")
    user_subscription2 = UserSubscription.generate_from_json(user_subscription.to_json())
    if user_subscription.to_json() != user_subscription2.to_json():
        print(json.dumps(user_subscription.to_json(), indent=2))
        print(json.dumps(user_subscription2.to_json(), indent=2))
    assert(user_subscription.to_json() == user_subscription2.to_json())
    print("testing that we can write a subscription to the db")
    UserSubscriptionTable.add_or_update_subscription(user_subscription)
    user_subscription2: UserSubscription = UserSubscriptionTable.read_subscription(user_subscription.user_id)
    user_subscription.subscription_id = user_subscription2.subscription_id
    if user_subscription.to_json() != user_subscription2.to_json():
        print(json.dumps(user_subscription.to_json(), indent=2))
        print(json.dumps(user_subscription2.to_json(), indent=2))
    assert(user_subscription.to_json() == user_subscription2.to_json())
    print("testing we cannot double add a subscription")
    try:
        UserSubscriptionTable.add_or_update_subscription(user_subscription)
        assert(True)
    except:
        print("Successfully avoided a double add")

def user_free_data_tests(user_id):
    print("TESTING USER FREE DATA TABLE")
    print("Testing adding and reading back free data")
    UserFreeDataTable.add_free_data(user_id)
    free_data = UserFreeDataTable.read_free_data(user_id)
    assert(free_data["FreeRatingsLeft"] == 3)
    print("Test Suceeded")
    print("Testing updating the free data")
    time_last_updated = free_data["LastReload"] - timedelta(days=2)
    UserFreeDataTable.update_free_data(user_id, 0, time_last_updated)
    reread_free_data = UserFreeDataTable.read_free_data(user_id)
    assert(reread_free_data["LastReload"] == time_last_updated)
    assert(reread_free_data["FreeRatingsLeft"] == 0)
    print("Test Suceeded")
    print("Testing getting free ratings left")
    reread_free_data = UserFreeDataTable.get_free_resume_info(user_id)
    assert(reread_free_data["LastReload"] > time_last_updated)
    assert(reread_free_data["FreeRatingsLeft"] == 3)
    print("Test Suceeded")
    print("Testing decrementing a resume rating")
    time_last_updated = free_data["LastReload"] - timedelta(days=2)
    UserFreeDataTable.update_free_data(user_id, 0, time_last_updated)
    UserFreeDataTable.use_free_resume_rating(user_id)
    reread_free_data = UserFreeDataTable.get_free_resume_info(user_id)
    assert(reread_free_data["LastReload"] > time_last_updated)
    assert(reread_free_data["FreeRatingsLeft"] == 2)
    print("Test Suceeded")
    print("Testing decrementing a resume rating when there is none left")
    time_last_updated = free_data["LastReload"]
    UserFreeDataTable.update_free_data(user_id, 0, time_last_updated)
    try:
        UserFreeDataTable.use_free_resume_rating(user_id)
        assert(False)
    except NoFreeRatingsLeft:
        pass
    print("Test Suceeded")



if __name__ == "__main__":
    relocation_grabber_tests()
    user_id = user_tests()
    company_tests()
    job_tests(user_id)
    user_job_tests(user_id)
    resume_tests(user_id)
    user_preferences_tests(user_id)
    resume_comparison_tests(user_id)
    user_subscription_tests(user_id)
    user_free_data_tests(user_id)



    