# restore.py
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

# Get configuration from environment variables and config file
# Reference: https://docs.python.org/3/library/configparser.html
from configparser import SafeConfigParser
config = SafeConfigParser(os.environ)
config.read('restore_config.ini')

# Initialize AWS clients
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
glacier = boto3.client('glacier', region_name=config['aws']['AwsRegionName'])
sqs = boto3.client('sqs', region_name=config['aws']['AwsRegionName'])
sns = boto3.client('sns', region_name=config['aws']['AwsRegionName'])
dynamodb = boto3.resource('dynamodb', region_name=config['aws']['AwsRegionName'])

table = dynamodb.Table(config['aws']['AwsDynamoDBTable'])

# Create and update a restore message in DynamoDB for the given job ID
def create_restore_message(job_id):
    restore_message = '''The restoration for this file is In Progress. However, this process takes
    5 hours, so be patient and check again later. '''
    try:
        # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/dynamodb/client/update_item.html
        response = table.update_item(
            Key={
                'job_id': job_id
            },
            UpdateExpression='SET #newAttr1 = :newValue1',
            ExpressionAttributeNames={
                '#newAttr1': 'restore_message'
            },
            ExpressionAttributeValues={
                ':newValue1': restore_message
            },
            ReturnValues='UPDATED_NEW'
        )
    except Exception as e:
        print(f"Failed to create restore message: {e}")

while True:
    # Receive messages from SQS queue
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/receive_message.html
    response = sqs.receive_message(
        QueueUrl=config['sqs']['RestoreQueueUrl'],
        AttributeNames=['All'],
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20
    )

    # Check if messages are received
    if 'Messages' in response:
        for message in response['Messages']:
            data = json.loads(json.loads(message['Body'])['Message'])
            job_id = data['job_id']
            archive_id = data['results_file_archive_id']

            try:
                # Attempt Expedited retrieval from Glacier
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/glacier/client/initiate_job.html
                glacier_response = glacier.initiate_job(
                    vaultName=config['aws']['GlacierVaultName'],
                    jobParameters={
                        'Type': 'archive-retrieval',
                        'ArchiveId': archive_id,
                        'Tier': 'Expedited',
                    }
                )

            except glacier.exceptions.InsufficientCapacityException:
                # Fallback to standard retrieval if expedited is unavailable
                glacier_response = glacier.initiate_job(
                    vaultName=config['aws']['GlacierVaultName'],
                    jobParameters={
                        'Type': 'archive-retrieval',
                        'ArchiveId': archive_id,
                        'Tier': 'Standard'
                    }
                )
            
            glacier_job_id = glacier_response['jobId']
            data['glacier_job_id'] = glacier_job_id
            
            # Post a restore message to DynamoDB
            create_restore_message(job_id)

            sns_message = json.dumps(data)
            try:
                # Publish message to SNS for thaw processing
                # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sns/client/publish.html
                sns_response = sns.publish(
                    TopicArn=config['sns']['ThawSnsArn'],
                    Message=sns_message,
                    Subject=job_id
                )
            except ClientError as e:
                print("unable to publish message to thaw")
            
            # Delete processed message from SQS queue
            # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/sqs/client/delete_message.html
            sqs.delete_message(
                QueueUrl=config['sqs']['RestoreQueueUrl'],
                ReceiptHandle=message['ReceiptHandle']
            )
            
### EOF
