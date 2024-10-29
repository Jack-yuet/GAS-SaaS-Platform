# config.py
#
# Copyright (C) 2011-2020 Vas Vasiliadis
# University of Chicago
#
# Set GAS configuration options based on environment
#
##
__author__ = 'Jack Yue <jackyue1@uchicago.edu>'

import os
import json
import boto3
import base64
from botocore.exceptions import ClientError

# Get the absolute path of the directory where the script is located
# Reference: https://docs.python.org/3/library/os.path.html#os.path.abspath
basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):
  # Set logging level
  GAS_LOG_LEVEL = os.environ['GAS_LOG_LEVEL'] \
    if ('GAS_LOG_LEVEL' in os.environ) else 'INFO'

  # Set log file path
  GAS_LOG_FILE_PATH = basedir + (os.environ['GAS_LOG_FILE_PATH'] \
    if ('GAS_LOG_FILE_PATH' in os.environ) else "/log")

  # Set log file name
  GAS_LOG_FILE_NAME = os.environ['GAS_LOG_FILE_NAME'] \
    if ('GAS_LOG_FILE_NAME' in os.environ) else "gas.log"

  # Set WSGI server
  WSGI_SERVER = 'werkzeug'
  CSRF_ENABLED = True

  # Host and port settings
  GAS_HOST_PORT = int(os.environ['GAS_HOST_PORT'])
  GAS_HOST_IP = os.environ['GAS_HOST_IP']
  GAS_APP_HOST = os.environ['GAS_APP_HOST']
  GAS_SERVER_NAME = f"{os.environ['GAS_HOST_IP']}:{os.environ['GAS_HOST_PORT']}"

  # AWS profile and region settings
  AWS_PROFILE_NAME = os.environ['AWS_PROFILE_NAME'] \
    if ('AWS_PROFILE_NAME' in os.environ) else None
  AWS_REGION_NAME = os.environ['AWS_REGION_NAME'] \
    if ('AWS_REGION_NAME' in os.environ) else "us-east-1"

  # Initialize AWS Secrets Manager client
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager.html
  asm = boto3.client('secretsmanager', region_name=AWS_REGION_NAME)

  try:
    # Retrieve Flask secret key from AWS Secrets Manager
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/secretsmanager.html#SecretsManager.Client.get_secret_value
    asm_response = asm.get_secret_value(SecretId='gas/web_server')
    flask_secret = json.loads(asm_response['SecretString'])
  except ClientError as e:
    print(f"Unable to retrieve Flask secret from ASM: {e}")
    raise e

  SECRET_KEY = flask_secret['flask_secret_key']

  try:
    # Retrieve RDS credentials from AWS Secrets Manager
    asm_response = asm.get_secret_value(SecretId='rds/accounts_database')
    rds_secret = json.loads(asm_response['SecretString'])
  except ClientError as e:
    print(f"Unable to retrieve accounts database credentials from ASM: {e}")
    raise e

  # Set SQLAlchemy database URI
  # Reference: https://docs.sqlalchemy.org/en/14/core/engines.html#database-urls
  SQLALCHEMY_DATABASE_TABLE = os.environ['ACCOUNTS_DATABASE_TABLE']
  SQLALCHEMY_DATABASE_URI = "postgresql://" + \
    rds_secret['username'] + ':' + rds_secret['password'] + \
    '@' + rds_secret['host'] + ':' + str(rds_secret['port']) + \
    '/' + SQLALCHEMY_DATABASE_TABLE
  SQLALCHEMY_TRACK_MODIFICATIONS = True

  try:
    # Retrieve Globus Auth credentials from AWS Secrets Manager
    asm_response = asm.get_secret_value(SecretId='globus/auth_client')
    globus_auth = json.loads(asm_response['SecretString'])
  except ClientError as e:
    print(f"Unable to retrieve Globus Auth credentials from ASM: {e}")
    raise e

  # Set the Globus Auth client ID and secret
  GAS_CLIENT_ID = globus_auth['gas_client_id']
  GAS_CLIENT_SECRET = globus_auth['gas_client_secret']
  GLOBUS_AUTH_LOGOUT_URI = "https://auth.globus.org/v2/web/logout"

  # Set AWS configurations
  AWS_SIGNED_REQUEST_EXPIRATION = 60
  AWS_S3_INPUTS_BUCKET = "mpcs-cc-gas-inputs"
  AWS_S3_RESULTS_BUCKET = "mpcs-cc-gas-results"
  AWS_S3_KEY_PREFIX = "jackyue1/"
  AWS_S3_ACL = "private"
  AWS_S3_ENCRYPTION = "AES256"
  AWS_GLACIER_VAULT = "mpcs-cc"
  AWS_SNS_JOB_REQUEST_TOPIC = \
    "arn:aws:sns:us-east-1:659248683008:jackyue1_job_requests"
  AWS_SNS_JOB_COMPLETE_TOPIC = \
    "arn:aws:sns:us-east-1:659248683008:jackyue1_job_results"
  AWS_SNS_RESTORE_ARCHIVE_TOPIC = \
    "arn:aws:sns:us-east-1:659248683008:jackyue1_glacier_restore"

  # Change the table name to your own
  AWS_DYNAMODB_ANNOTATIONS_TABLE = "jackyue1_annotations"

  # Change the email address to your username
  MAIL_DEFAULT_SENDER = "jackyue1@mpcs-cc.com"

  # Time before free user results are archived (in seconds)
  FREE_USER_DATA_RETENTION = 300

class DevelopmentConfig(Config):
  # Enable debugging and set log level to DEBUG for development
  DEBUG = True
  GAS_LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
  # Set production configuration
  DEBUG = False
  GAS_LOG_LEVEL = 'INFO'
  WSGI_SERVER = 'gunicorn.error'

class StagingConfig(Config):
  # Set staging configuration
  STAGING = True

class TestingConfig(Config):
  # Set testing configuration
  TESTING = True

### EOF
