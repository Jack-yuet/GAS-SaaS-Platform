# archive.py
#
# NOTE: This file lives on the Utils instance
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Jack Yue <jackyue1@uchicago.edu>'

import boto3
import json
from botocore.exceptions import ClientError
import os
import sys

# Import utility helpers
# Reference: https://docs.python.org/3/library/sys.html#sys.path
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers
from configparser import SafeConfigParser

# Load configuration from environment variables and config file
# Reference: https://docs.python.org/3/library/configparser.html
config = SafeConfigParser(os.environ)
config.read('archive_config.ini')

# Initialize AWS clients
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
glacier = boto3.client('glacier', region_name=config['aws']['AwsRegionName'])
sqs = boto3.client('sqs', region_name=config['aws']['AwsRegionName'])
s3 = boto3.client('s3', region_name=config['aws']['AwsRegionName'])
dynamodb = boto3.resource('dynamodb', region_name=config['aws']['AwsRegionName'])
table = dynamodb.Table(config['aws']['AwsDynamoDBTable'])

while True:
    # Receive messages from SQS queue
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/receive_message.html
    response = sqs.receive_message(
        QueueUrl=config['sqs']['GlacierQueueUrl'],
        AttributeNames=['All'],
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20
    )
    
    # Check if messages are received
    if 'Messages' in response:
        for message in response['Messages']:
            data = json.loads(json.loads(message['Body'])['Message'])
            bucket_name = data['s3_results_bucket']
            result_key = data['s3_key_result_file']
            job_id = data['job_id']
            user_id = data['user_id']

            # Check for premium user
            profile = helpers.get_user_profile(id=user_id)
            if profile[4] == 'premium_user':
                # Deleting message for premium user
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/delete_message.html
                sqs.delete_message(
                    QueueUrl=config['sqs']['GlacierQueueUrl'],
                    ReceiptHandle=message['ReceiptHandle']
                )
                continue
            
            # Retrieve results file from S3
            try:
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/s3/client/get_object.html
                s3_object = s3.get_object(
                    Bucket=bucket_name,
                    Key=result_key,
                )
                stream = s3_object['Body'].read()
            except Exception as e:
                print("error: Failed to retrieve result file from S3")
                print("details: " + str(e))

            # Upload result file to Glacier
            try:
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/glacier/client/upload_archive.html
                glacier_response = glacier.upload_archive(
                    vaultName=config['aws']['GlacierVaultName'],
                    body=stream
                )
                archive_id = glacier_response['archiveId']
            except Exception as e:
                print("error: Failed to upload result file to Glacier")
                print("details: " + str(e))

            # Update DynamoDB with archive ID
            try:
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/dynamodb/client/update_item.html
                response = table.update_item(
                    Key={
                        'job_id': job_id
                    },
                    UpdateExpression='SET #newAttr1 = :newValue1',
                    ExpressionAttributeNames={
                        '#newAttr1': 'results_file_archive_id'
                    },
                    ExpressionAttributeValues={
                        ':newValue1': archive_id
                    },
                    ReturnValues='UPDATED_NEW'
                )
            except Exception as e:
                print("error: Failed to update DynamoDB")
                print("details: " + str(e))

            # Delete the result file from S3
            # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/s3/client/delete_object.html
            s3.delete_object(
                Bucket=bucket_name,
                Key=result_key
            )
        
            # Delete processed message from SQS queue
            # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/delete_message.html
            sqs.delete_message(
                QueueUrl=config['sqs']['GlacierQueueUrl'],
                ReceiptHandle=message['ReceiptHandle']
            )

### EOF
