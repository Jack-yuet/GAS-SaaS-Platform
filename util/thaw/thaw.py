# thaw.py
#
# NOTE: This file lives on the Utils instance
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
##
__author__ = 'Jack Yue <jackyue1@uchicago.edu>'

import os
import sys
import boto3
import json
from botocore.exceptions import ClientError

# Import utility helpers
# Reference: https://docs.python.org/3/library/sys.html#sys.path
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration from environment variables and config file
# Reference: https://docs.python.org/3/library/configparser.html
from configparser import SafeConfigParser
config = SafeConfigParser(os.environ)
config.read('thaw_config.ini')

# Initialize AWS clients
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
glacier = boto3.client('glacier', region_name=config['aws']['AwsRegionName'])
sqs = boto3.client('sqs', region_name=config['aws']['AwsRegionName'])
s3 = boto3.client('s3', region_name=config['aws']['AwsRegionName'])
dynamodb = boto3.resource('dynamodb', region_name=config['aws']['AwsRegionName'])
table = dynamodb.Table(config['aws']['AwsDynamoDBTable'])

# Remove the 'restore_message' and 'results_file_archive_id' attributes from DynamoDB for the given job ID
def delete_archive_parameters(job_id):
    try:
        # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/dynamodb/client/update_item.html
        response = table.update_item(
            Key={
                'job_id': job_id
            },
            UpdateExpression='REMOVE restore_message, results_file_archive_id',
            ReturnValues='UPDATED_NEW'
        )
    except Exception as e:
        print(f"Failed to delete attributes: {e}")

while True:
    # Polling Thaw messages using long polling
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/receive_message.html
    response = sqs.receive_message(
        QueueUrl=config['sqs']['ThawQueueUrl'],
        AttributeNames=['All'],
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20
    )

    # Check if messages are received
    if 'Messages' in response:
        for message in response['Messages']:
            # Check for restoration status
            data = json.loads(json.loads(message['Body'])['Message'])
            glacier_job_id = data['glacier_job_id']
            try:
                # Describe Glacier job to check completion status
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/glacier/client/describe_job.html
                job_description = glacier.describe_job(
                    vaultName=config['aws']['GlacierVaultName'],
                    jobId=glacier_job_id
                )
            except ClientError as e:
                print(f"unable to find glacier job: {e}")

            # If job is not completed, continue polling
            if not job_description['Completed']:
                continue
            else:
                job_id = data['job_id']
                archive_id = data['results_file_archive_id']
                result_key = data['s3_key_result_file']
                bucket_name = data['s3_results_bucket']

                # Load job output stream from Glacier
                try:
                    # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/glacier/client/get_job_output.html
                    job_output_response = glacier.get_job_output(
                        vaultName=config['aws']['GlacierVaultName'],
                        jobId=glacier_job_id
                    )
                except ClientError as e:
                    print(f"unable to download job {job_id}: {e}")
                
                job_output_stream = job_output_response['body']

                # Uploading stream to S3 results bucket
                try:
                    # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/s3/client/upload_fileobj.html
                    s3.upload_fileobj(
                        job_output_stream,
                        bucket_name,
                        result_key
                    )
                except ClientError as e:
                    print(f"Unable to upload restored result as {data['s3_key_result_file']}: {e}")
                
                # Delete the archive from Glacier
                try:
                    # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/glacier/client/delete_archive.html
                    glacier.delete_archive(
                        vaultName=config['aws']['GlacierVaultName'],
                        archiveId=archive_id
                    )
                except Exception as e:
                    print(f"An error occurred when deleting archive: {e}")
                
                # Delete restore message from DynamoDB
                delete_archive_parameters(job_id)

                # Delete processed message from SQS queue
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/delete_message.html
                sqs.delete_message(
                    QueueUrl=config['sqs']['ThawQueueUrl'],
                    ReceiptHandle=message['ReceiptHandle']
                )

### EOF
