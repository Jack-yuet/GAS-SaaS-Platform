# views.py
#
# Copyright (C) 2011-2020 Vas Vasiliadis
# University of Chicago
#
# Application logic for the GAS
#
##
__author__ = 'Jack Yue <jackyue1@uchicago.edu>'

import uuid
import time
import json
from datetime import datetime
from boto3.dynamodb.conditions import Key
from botocore.client import Config
import boto3
from botocore.exceptions import ClientError

from flask import (abort, flash, redirect, render_template,
  request, session, url_for, jsonify)

from gas import app, db
from decorators import authenticated, is_premium
from auth import get_profile, update_profile


"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document.

Note: You are welcome to use this code instead of your own
but you can replace the code below with your own if you prefer.
"""
@app.route('/annotate', methods=['GET'])
@authenticated
def annotate():
  # Create a session client to the S3 service
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client
  s3 = boto3.client('s3',
    region_name=app.config['AWS_REGION_NAME'],
    config=Config(signature_version='s3v4'))

  bucket_name = app.config['AWS_S3_INPUTS_BUCKET']
  user_id = session['primary_identity']

  # Generate unique ID to be used as S3 key (name)
  # Reference: https://docs.python.org/3/library/uuid.html
  key_name = app.config['AWS_S3_KEY_PREFIX'] + user_id + '/' + \
    str(uuid.uuid4()) + '~${filename}'
  redirect_url = str(request.url) + '/job'
  encryption = app.config['AWS_S3_ENCRYPTION']
  acl = app.config['AWS_S3_ACL']
  fields = {
    "success_action_redirect": redirect_url,
    "x-amz-server-side-encryption": encryption,
    "acl": acl
  }
  conditions = [
    ["starts-with", "$success_action_redirect", redirect_url],
    {"x-amz-server-side-encryption": encryption},
    {"acl": acl}
  ]
  try:
    # Generate a presigned URL for S3 upload
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.generate_presigned_post
    presigned_post = s3.generate_presigned_post(
      Bucket=bucket_name, 
      Key=key_name,
      Fields=fields,
      Conditions=conditions,
      ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'])
  except ClientError as e:
    app.logger.error(f"Unable to generate presigned URL for upload: {e}")
    return abort(500)
  return render_template('annotate.html', s3_post=presigned_post)


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.

Note: Update/replace the code below with your own from previous
homework assignments
"""
@app.route('/annotate/job', methods=['GET'])
@authenticated
# Parse S3 redirect request and create a job in DynamoDB
def create_annotation_job_request():
  bucket_name = str(request.args.get('bucket'))
  key = str(request.args.get('key'))
  job_id = key.split('~')[0].split('/')[-1]
  input_file_name = key.split('~')[-1]
  user_email = session['email']
  user_id = session['primary_identity']
  timestamp = int(time.time())
  # Initialize DynamoDB resource
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.ServiceResource
  dynamo = boto3.resource('dynamodb')
  table = dynamo.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])

  data = {
    "job_id": job_id,
    "user_id": user_id,
    "user_email": user_email,
    "input_file_name": input_file_name,
    "s3_inputs_bucket": bucket_name,
    "s3_key_input_file": key,
    "submit_time": timestamp,
    "job_status": "PENDING"
  }

  try:
    # Insert the job data into DynamoDB
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.put_item
    dynamo_response = table.put_item(Item=data)
  except Exception as e:
    return jsonify({
      "code": 500,
      "status": "error",
      "message": str(e)
    }), 500
  message = json.dumps(data)
  sns_client = boto3.client('sns', 
    region_name=app.config['AWS_REGION_NAME'])
  try:
    # Publish a message to the SNS topic
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#SNS.Client.publish
    sns_response = sns_client.publish(
      TopicArn=app.config['AWS_SNS_JOB_REQUEST_TOPIC'],
      Message=message,
      Subject=job_id
    )
  except Exception as e:
    return jsonify({
      "code": 500,
      "status": "error",
      "message": str(e)
    }), 500
  return render_template('annotate_confirm.html', job_id=job_id)


@app.route('/annotations', methods=['GET'])
@authenticated
# List all annotation jobs for the authenticated user
def annotations_list():
  dynamo = boto3.resource('dynamodb')
  table = dynamo.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])

  # Query DynamoDB for all jobs belonging to the user
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.query
  response = table.query(
    IndexName='user_id_index',
    KeyConditionExpression=Key('user_id').eq(session['primary_identity']),
    ExpressionAttributeValues={
      ':partitionkeyval': session['primary_identity']
    }
  )
  annotations = response['Items']
  for annotation in annotations:
    submit_dt = datetime.utcfromtimestamp(annotation['submit_time'])
    annotation['submit_time'] = submit_dt.strftime('%Y-%m-%d %H:%M')

  return render_template('annotations.html', annotations=annotations)


@app.route('/annotations/<id>', methods=['GET'])
@authenticated
# Display details for a specific annotation job
def annotation_details(id):
  free_access_expired = False
  dynamo = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  table = dynamo.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])

  # Query the DynamoDB table for the job details
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/Table.html#DynamoDB.Table.query
  response = table.query(
    KeyConditionExpression='job_id = :partitionkeyval',
    ExpressionAttributeValues={
      ':partitionkeyval': id
    }
  )
  annotation = response['Items'][0]
  if annotation['user_id'] != session['primary_identity']:
    return jsonify({
      "code": 500,
      "status": "error",
      "message": "Not Authorized to View this Job"
    }), 500

  submit_dt = datetime.utcfromtimestamp(annotation['submit_time'])
  annotation['submit_time'] = submit_dt.strftime('%Y-%m-%d %H:%M')
  s3 = boto3.client('s3',
    region_name=app.config['AWS_REGION_NAME'],
    config=Config(signature_version='s3v4'))
  try:
    # Generate a presigned URL for downloading the input file
    # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.generate_presigned_url
    input_url = s3.generate_presigned_url(
      'get_object',
      Params={
        'Bucket': annotation['s3_inputs_bucket'],
        'Key': annotation['s3_key_input_file']
      },
      ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION']
    )
  except ClientError as e:
    app.logger.error(f"Unable to generate presigned URL for download: {e}")
    return abort(500)
  annotation['input_file_url'] = input_url
  if annotation['job_status'] == 'COMPLETED':
    complete_dt = datetime.utcfromtimestamp(annotation['complete_time'])
    annotation['complete_time'] = submit_dt.strftime('%Y-%m-%d %H:%M')
    if 'restore_message' not in annotation:
      if 'results_file_archive_id' in annotation:
        free_access_expired = True
      else:
        try:
          # Generate a presigned URL for downloading the result file
          # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.generate_presigned_url
          results_url = s3.generate_presigned_url(
            'get_object',
            Params={
              'Bucket': annotation['s3_results_bucket'],
              'Key': annotation['s3_key_result_file']
            },
            ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION']
          )
        except ClientError as e:
          app.logger.error(f"Unable to generate presigned URL for download: {e}")
          return abort(500)
        annotation['result_file_url'] = results_url
  return render_template('annotation_details.html', 
                         annotation=annotation,
                         free_access_expired=free_access_expired)



@app.route('/annotations/<id>/log', methods=['GET'])
@authenticated
# Display log file contents for a specific annotation job
def annotation_log(id):
  dynamo = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  table = dynamo.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])

  # Query the DynamoDB table for the log file details
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/Table.html#DynamoDB.Table.query
  response = table.query(
    KeyConditionExpression='job_id = :partitionkeyval',
    ExpressionAttributeValues={
      ':partitionkeyval': id
    }
  )
  annotation = response['Items'][0]
  s3 = boto3.client('s3',
    region_name=app.config['AWS_REGION_NAME'],
    config=Config(signature_version='s3v4'))
  
  # Retrieve the log file from S3
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.get_object
  response = s3.get_object(
    Bucket=annotation['s3_results_bucket'],
    Key=annotation['s3_key_log_file']
  )
  content = response['Body'].read().decode('utf-8')
  return render_template('view_log.html', log_file_contents=content, job_id=id)



@app.route('/subscribe', methods=['GET', 'POST'])
@authenticated
def subscribe():
  # Handle subscription form display and submission
  if (request.method == 'GET'):
    # Display form to get subscriber credit card info
    if (session.get('role') == "free_user"):
      return render_template('subscribe.html')
    else:
      return redirect(url_for('profile'))

  elif (request.method == 'POST'):
    # Update user role to allow access to paid features
    update_profile(
      identity_id=session['primary_identity'],
      role="premium_user"
    )
    session['role'] = "premium_user"

    # Request restoration of the user's data from Glacier
    dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
    table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
    try:
      # Query DynamoDB for user data
      # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/Table.html#DynamoDB.Table.query
      response = table.query(
        IndexName='user_id_index',
        KeyConditionExpression='user_id = :partitionkeyval',
        ExpressionAttributeValues={
          ':partitionkeyval': session['primary_identity']
        }
      )
    except ClientError as e:
      app.logger.error(f"Unable to query data: {e}")
      return abort(500)
    annotations = response['Items']
    for annotation in annotations:
      sns = boto3.client('sns', region_name=app.config['AWS_REGION_NAME'])
      # Restore archived files
      if 'results_file_archive_id' in annotation:
        job_id = annotation['job_id']
        annotation['submit_time'] = int(annotation['submit_time'])
        annotation['complete_time'] = int(annotation['complete_time'])
        message = json.dumps(annotation)
        try:
          # Publish a message to SNS for restoration
          # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#SNS.Client.publish
          sns_response = sns.publish(
            TopicArn=app.config['AWS_SNS_RESTORE_ARCHIVE_TOPIC'],
            Message=message,
            Subject=job_id
          )
        except ClientError as e:
          app.logger.error(f"Unable to post message for restoration process: {e}")
          return abort(500)
    return render_template('subscribe_confirm.html') 



@app.route('/unsubscribe', methods=['GET'])
@authenticated
def unsubscribe():
  # Reset subscription
  # Reference: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
  update_profile(
    identity_id=session['primary_identity'],
    role="free_user"
  )
  return redirect(url_for('profile'))



"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Home page
"""
@app.route('/', methods=['GET'])
def home():
  return render_template('home.html')

"""Login page; send user to Globus Auth
"""
@app.route('/login', methods=['GET'])
def login():
  app.logger.info(f"Login attempted from IP {request.remote_addr}")
  # If user requested a specific page, save it session for redirect after auth
  if (request.args.get('next')):
    session['next'] = request.args.get('next')
  return redirect(url_for('authcallback'))

"""404 error handler
"""
@app.errorhandler(404)
def page_not_found(e):
  return render_template('error.html', 
    title='Page not found', alert_level='warning',
    message="The page you tried to reach does not exist. \
      Please check the URL and try again."
    ), 404

"""403 error handler
"""
@app.errorhandler(403)
def forbidden(e):
  return render_template('error.html',
    title='Not authorized', alert_level='danger',
    message="You are not authorized to access this page. \
      If you think you deserve to be granted access, please contact the \
      supreme leader of the mutating genome revolutionary party."
    ), 403

"""405 error handler
"""
@app.errorhandler(405)
def not_allowed(e):
  return render_template('error.html',
    title='Not allowed', alert_level='warning',
    message="You attempted an operation that's not allowed; \
      get your act together, hacker!"
    ), 405

"""500 error handler
"""
@app.errorhandler(500)
def internal_error(error):
  return render_template('error.html',
    title='Server error', alert_level='danger',
    message="The server encountered an error and could \
      not process your request."
    ), 500

### EOF
