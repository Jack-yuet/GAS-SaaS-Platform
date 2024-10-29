import boto3
import json
import os
import subprocess
from decimal import Decimal
from configparser import SafeConfigParser

# Load configuration from environment variables and config file
# Reference: https://docs.python.org/3/library/configparser.html
config = SafeConfigParser(os.environ)
config.read('ann_config.ini')

# Initialize SQS client
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html
sqs_client = boto3.client('sqs', region_name=config['aws']['AwsRegionName'])

# Set download directory
download_dir = os.getcwd() + '/downloads'

def update_item(job_id):
    # Update job status to 'RUNNING' in DynamoDB if currently 'PENDING'
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(config['aws']['AwsDynamoDBTable'])

    # Retrieve job status from DynamoDB
    status_response = table.get_item(Key={'job_id': job_id})
    if status_response['Item']['job_status'] == 'PENDING':
        # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
        response = table.update_item(
            Key={
                'job_id': job_id
            },
            UpdateExpression='SET job_status = :val1',
            ExpressionAttributeValues={
                ':val1': 'RUNNING'
            },
            ReturnValues='UPDATED_NEW'
        )
        print(response)

while True:
    # Receive messages from SQS queue
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#SQS.Client.receive_message
    response = sqs_client.receive_message(
        QueueUrl=config['aws']['SqsQueueURL'],
        AttributeNames=['All'],
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20
    )

    # Check if messages are received
    if 'Messages' in response:
        for message in response['Messages']:
            print("Received Message.")
            data = json.loads(json.loads(message['Body'])['Message'])

            # Create download directory if it does not exist
            # Reference: https://docs.python.org/3/library/os.html
            if not os.path.exists(download_dir):
                os.makedirs(download_dir)
            download_path = download_dir + '/' + data['input_file_name']
            s3_client = boto3.client('s3', region_name=config['aws']['AwsRegionName'])

            # Download file from S3
            # Reference: https://boto3.amazonaws.com/v1/documentation/api/1.26.94/reference/services/s3/client/download_file.html
            try:
                s3_client.download_file(
                    data['s3_inputs_bucket'],
                    data['s3_key_input_file'],
                    download_path
                )
            except Exception as e:
                print("error: Failed to download file from S3")
                print("details: " + str(e))
            
            # Update job status and process the file
            try:
                update_item(data['job_id'])
                subprocess.Popen([
                    "python",
                    os.getcwd() + "/run.py",
                    download_path,
                    data['job_id'],
                    data['s3_key_input_file']
                ])
            except Exception as e:
                print("Processing file failed")
                print("details: " + str(e))
            
            # Delete the processed message from SQS queue
            sqs_client.delete_message(
                QueueUrl=config['aws']['SqsQueueURL'],
                ReceiptHandle=message['ReceiptHandle']
            )
            print("Deleted Message.")