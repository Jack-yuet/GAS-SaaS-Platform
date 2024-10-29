import sys
import time
import driver
import os
import boto3
import json
import jsonify

from configparser import SafeConfigParser

"""A rudimentary timer for coarse-grained profiling
"""
class Timer(object):
  def __init__(self, verbose=True):
    self.verbose = verbose

  def __enter__(self):
    self.start = time.time()
    return self

  def __exit__(self, *args):
    self.end = time.time()
    self.secs = self.end - self.start
    if self.verbose:
      print(f"Approximate runtime: {self.secs:.2f} seconds")


# Upload a file to the specified S3 bucket
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.upload_file
def upload_file(bucket_name, file_path, key):
  try:
    s3_client.upload_file(file_path, bucket_name, key)
  except Exception as e:
    print(f"Error uploading file to s3: {e}")

# Delete a local file
# Reference: https://docs.python.org/3/library/os.html#os.remove
def delete_local_file(file_path):
  try:
    os.remove(file_path)
    print(f"Deleted local file {file_path}")
  except Exception as e:
    print("Error deleting local file: {e}")

# Update an item in DynamoDB with job details
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html
def update_item(job_id, results_bucket, result_file, log_file):
  try:
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
    response = table.update_item(
      Key={
        'job_id': job_id
      },
      UpdateExpression='SET #newAttr1 = :newValue1, #newAttr2 = :newValue2, #newAttr3 = :newValue3, #newAttr4 = :newValue4, job_status = :existValue',
      ExpressionAttributeNames={
        '#newAttr1': 's3_results_bucket',
        '#newAttr2': 's3_key_result_file',
        '#newAttr3': 's3_key_log_file',
        '#newAttr4': 'complete_time'
      },
      ExpressionAttributeValues={
        ':newValue1': results_bucket,
        ':newValue2': result_file,
        ':newValue3': log_file,
        ':newValue4': int(time.time()),
        ':existValue': 'COMPLETED'
      },
      ReturnValues='UPDATED_NEW'
    )
    print(response)
  except Exception as e:
    print(f"Error updating item in DynamoDB: {e}")

# Publish messages to SNS topics
# Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html
def publish_messages(job_id):
  try:
    # Retrieve job details from DynamoDB
    status_response = table.get_item(Key={'job_id': job_id})
    data = status_response.get('Item', None)
    
    if data:
      data['submit_time'] = int(data['submit_time'])
      data['complete_time'] = int(data['complete_time'])
      message = json.dumps(data)
      
      # Publish message to Results SNS topic
      # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns/client/publish.html
      sns_response = sns_client.publish(
        TopicArn=config['sns']['ResultsArn'],
        Message=message,
        Subject=job_id
      )
      print("email message published")
      print(sns_response)
      
      # Publish message to Glacier SNS topic
      sns_response = sns_client.publish(
        TopicArn=config['sns']['GlacierArn'],
        Message=message,
        Subject=job_id
      )
      print("glacier message published")
      print(sns_response)
    else:
      print(f"Job ID: {job_id} item not found")
  except Exception as e:
    print(f"Failed to publish SNS messages: {e}")

if __name__ == '__main__':
  if len(sys.argv) > 1:
    input_file_name = sys.argv[1]
    job_id = sys.argv[2]
    with Timer():
      driver.run(input_file_name, 'vcf')
      results_file = input_file_name[:-4] + '.annot.vcf'
      log_file = input_file_name + '.count.log'
      input_file = input_file_name
      results_bucket = config['aws']['AwsResultsBucket']
      results_key = sys.argv[3].split('~')[0] + '~' + results_file.split('/')[-1]
      log_key = sys.argv[3].split('~')[0] + '~' + log_file.split('/')[-1]
      
      # Upload results and log files to S3
      upload_file(results_bucket, results_file, results_key)
      upload_file(results_bucket, log_file, log_key)
      
      # Update DynamoDB with job details
      update_item(job_id, results_bucket, results_key, log_key)
      
      # Delete local files
      delete_local_file(results_file)
      delete_local_file(log_file)
      delete_local_file(input_file)
      
      # Publish messages to SNS topics
      publish_messages(job_id)
  else:
    print("A valid .vcf file must be provided.")

### EOF
