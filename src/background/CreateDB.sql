DROP DATABASE IF EXISTS JOBDB;
CREATE DATABASE JOBDB;
USE JOBDB;

CREATE TABLE User (
    UserId VARCHAR(36) NOT NULL,
    Email VARCHAR(255) NOT NULL UNIQUE,
    -- if user auths with google we dont store password
    Password VARCHAR(255),
    GoogleId VARCHAR(255) UNIQUE,
    FirstName VARCHAR(255) NOT NULL,
    LastName VARCHAR(255) NOT NULL,
    Salt VARCHAR(50),
CONSTRAINT User_PK PRIMARY KEY (UserId)
);
CREATE TABLE UserSubscription
(
    SubscriptionId INT AUTO_INCREMENT,
    UserId VARCHAR(36) NOT NULL,
    Price INT NOT NULL,
    SubscriptionType VARCHAR(50) NOT NULL,
    StripeCustomerId VARCHAR(255) NOT NULL,
    StripeSubscriptionId VARCHAR(255) NOT NULL,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CurrentPeriodEnd TIMESTAMP,
    CanceledAt TIMESTAMP,
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
CONSTRAINT UserSubscription_PK PRIMARY KEY (SubscriptionId),
CONSTRAINT UserSubscription_FK FOREIGN KEY (UserId) REFERENCES User(UserId) ON DELETE CASCADE
);
CREATE TABLE UserFreeData
(
    UserIdFk VARCHAR(36),
    Email VARCHAR(255),
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FreeRatingsLeft TINYINT DEFAULT 3,
    LastReload TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
CONSTRAINT UserFreeData_PK PRIMARY KEY (UserIdFk)
);
CREATE TABLE Company
(
    CompanyName VARCHAR(255) NOT NULL UNIQUE,
    BusinessOutlookRating DECIMAL(3, 2) default 0,
    CareerOpportunitiesRating DECIMAL(2, 1) default 0,
    CeoRating DECIMAL(3, 2) default 0,
    CompensationAndBenefitsRating DECIMAL(2, 1) default 0,
    CultureAndValuesRating DECIMAL(2, 1) default 0,
    DiversityAndInclusionRating DECIMAL(2, 1) default 0,
    SeniorManagementRating DECIMAL(2, 1) default 0,
    WorkLifeBalanceRating DECIMAL(2, 1) default 0,
    OverallRating DECIMAL(2, 1) default 0,
    -- timestamp added to keep our data current, if data is older than lets say a month
    -- we regrab it
    TimeAdded timestamp default current_timestamp not null,
    GlassdoorUrl VARCHAR(2083),
CONSTRAINT Company_PK PRIMARY KEY (CompanyName)
);
CREATE TABLE Job
(
    JobId VARCHAR(128) NOT NULL,
    Applicants TINYINT,
    CareerStage VARCHAR(20),
    Job VARCHAR(255),
    Company VARCHAR(255) NOT NULL,
    Description LONGBLOB,
    -- uuid to keywords, one to many
    PaymentBase DECIMAL(9, 2),
    PaymentFreq VARCHAR(8),
    PaymentHigh DECIMAL(9, 2),
    LocationStr VARCHAR(50),
    Mode VARCHAR(15),
    JobPostedAt TIMESTAMP(3),
    TimeAdded TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
CONSTRAINT Job_PK PRIMARY KEY (JobId),
CONSTRAINT Job_foreign_key_company FOREIGN KEY (Company) REFERENCES Company(CompanyName) ON DELETE CASCADE
);
CREATE TABLE UserJob
(
    -- Hash of job ID and user ID, ensures both arent already in db
    UserJobId VARCHAR(36) NOT NULL UNIQUE,
    JobId VARCHAR(128) NOT NULL,
    UserId VARCHAR(36) NOT NULL,
    IsFavorite BOOLEAN NOT NULL DEFAULT FALSE,
    HasApplied BOOLEAN NOT NULL DEFAULT FALSE,
    TimeSelected TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
CONSTRAINT UserJob_PK PRIMARY KEY (UserJobId),
CONSTRAINT UserJob_FK1 FOREIGN KEY (JobId) REFERENCES Job(JobId) ON DELETE CASCADE,
CONSTRAINT UserJob_FK2 FOREIGN KEY (UserId) REFERENCES User(UserId) ON DELETE CASCADE
);
CREATE TABLE JobLocation
(
    QueryStr VARCHAR(70),
    JobIdFK VARCHAR(128),
    AddressStr VARCHAR(255),
    City VARCHAR(255),
    ZipCode VARCHAR(255),
    -- to be safe
    StateCode VARCHAR(255),
    Latitude DECIMAL(10,7) NOT NULL,
    Longitude DECIMAL(10,7) NOT NULL,
CONSTRAINT JobLocation_PK PRIMARY KEY (QueryStr),
CONSTRAINT JobLocation_FK1 FOREIGN KEY (JobIdFK) REFERENCES Job(JobId) ON DELETE CASCADE
);
CREATE TABLE UserLocation
(
    UserIdFk VARCHAR(36),
    AddressStr VARCHAR(255),
    City VARCHAR(255),
    ZipCode VARCHAR(255),
    StateCode VARCHAR(255),
    Latitude DECIMAL(5,2) NOT NULL,
    Longitude DECIMAL(5,2) NOT NULL,
CONSTRAINT UserLocation_PK PRIMARY KEY (UserIdFk),
CONSTRAINT UserLocation_FK FOREIGN KEY (UserIdFk) REFERENCES User(UserId) ON DELETE CASCADE
);
CREATE TABLE Resumes
(
    Id INT AUTO_INCREMENT,
    Name VARCHAR(50),
    UserId VARCHAR(36) NOT NULL,
    FileName VARCHAR(255) NOT NULL,
    FileType VARCHAR(50) NOT NULL,
    FileContent LONGBLOB NOT NULL,
    FileText LONGBLOB NOT NULL,
    UploadDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    IsDefault BOOLEAN NOT NULL,
CONSTRAINT Resumes_PK PRIMARY KEY (id),
CONSTRAINT Resumes_FK FOREIGN KEY (UserId) REFERENCES User(UserId) ON DELETE CASCADE
);
CREATE TABLE UserPreferences
(
    UserIdFk VARCHAR(36) NOT NULL,
    DesiredPay DECIMAL(9, 2) NOT NULL,
    DesiredPaymentFreq VARCHAR(8) NOT NULL,
    DesiredCommute TINYINT,
    DesiresRemote BOOLEAN NOT NULL,
    DesiresHybrid BOOLEAN NOT NULL,
    DesiresOnsite BOOLEAN NOT NULL,
    DesiredCareerStage VARCHAR(20) NOT NULL,
    AutoActiveOnNewJobLoaded BOOLEAN NOT NULL,
    AutoCompareResumeOnNewJobLoaded BOOLEAN NOT NULL,
    SaveEveryJobByDefault BOOLEAN NOT NULL,
CONSTRAINT UserPreferences_PK PRIMARY KEY (UserIdFk),
CONSTRAINT UserPreferences_FK FOREIGN KEY (UserIdFk) REFERENCES User(UserId) ON DELETE CASCADE
);
CREATE TABLE KeywordList
(
    UserIdFk VARCHAR(36) NOT NULL,
    PositiveKeyWord1 VARCHAR(255),
    PositiveKeyWord2 VARCHAR(255),
    PositiveKeyWord3 VARCHAR(255),
    PositiveKeyWord4 VARCHAR(255),
    PositiveKeyWord5 VARCHAR(255),
    PositiveKeyWord6 VARCHAR(255),
    PositiveKeyWord7 VARCHAR(255),
    PositiveKeyWord8 VARCHAR(255),
    PositiveKeyWord9 VARCHAR(255),
    PositiveKeyWord10 VARCHAR(255),
    NegativeKeyWord1 VARCHAR(255),
    NegativeKeyWord2 VARCHAR(255),
    NegativeKeyWord3 VARCHAR(255),
    NegativeKeyWord4 VARCHAR(255),
    NegativeKeyWord5 VARCHAR(255),
    NegativeKeyWord6 VARCHAR(255),
    NegativeKeyWord7 VARCHAR(255),
    NegativeKeyWord8 VARCHAR(255),
    NegativeKeyWord9 VARCHAR(255),
    NegativeKeyWord10 VARCHAR(255),
CONSTRAINT UserKeywords_PK PRIMARY KEY (UserIdFk),
CONSTRAINT UserKeywords_FK FOREIGN KEY (UserIdFk) REFERENCES User(UserId) ON DELETE CASCADE
);
CREATE TABLE EmailConfirmation
(
    Email VARCHAR(255),
    ConfirmationCode VARCHAR(6),
    ForgotPassword BOOLEAN DEFAULT FALSE,
    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
CONSTRAINT EmailConfirmation_PK PRIMARY KEY (Email)
);