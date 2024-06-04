import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL') or 'mysql+pymysql://admin:March123!!!@database-1.c18ky06gcpu2.ap-south-1.rds.amazonaws.com:3306/APNAFUNDA'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'March123!!!'
    SESSION_TYPE = 'sqlalchemy'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_SQLALCHEMY_TABLE = 'sessions'
