# GAS: SaaS Platform based on AWS service

## Overview
The **Genomic Annotation Service (GAS)** is a robust Software-as-a-Service (SaaS) platform designed to meet the growing demand for scalable and flexible data services in the genomics field. GAS provides tiered access to advanced genomic annotation tools, offering seamless data submission, notifications, and secure access to results.

## Key Features

### User Authentication & Tiered Access
- **Authentication**: Secure login using Globus Auth.
- **Access Tiers**: Differentiated access for **Free** and **Premium** users, granting varied privileges.
  
### Annotation Job Submission
- **Easy Submission**: Streamlined submission process for genomic data annotation.
- **Usage Limits**: Job size restrictions for Free-tier users to ensure resource availability.

### Notification System
- **Real-Time Alerts**: Users receive email notifications upon job completion via AWS Lambda and SNS/SQS integrations.

### Data Archiving & Retrieval
- **Free-Tier Data Archiving**: Completed jobs for Free users are archived to **AWS Glacier**.
- **Retrieval for Premium Users**: Retrieval of archived data available as a Premium feature.

### Scalability & Load Handling
- **Elastic Infrastructure**: Auto-scaling and load balancing for web servers and annotation services.
- **Cost-Effectiveness**: Optimized to handle high traffic without compromising on performance or cost.

---

## AWS Tools & Services Used

### Compute & Networking
- **EC2**: Hosts both the web and annotation servers.
- **Elastic Load Balancing (ELB)**: Distributes traffic efficiently across instances.

### Data Storage & Archiving
- **S3**: Primary storage for submitted and processed data.
- **AWS Glacier**: Cost-effective archiving solution for Free-tier data, preserving storage efficiency.

### Data & Job Management
- **DynamoDB**: Stores job metadata, enabling efficient tracking and access control.

### Notifications
- **SNS & SQS**: Used to manage notification queues and process job completion alerts.
- **AWS Lambda**: Triggers serverless email notifications, reducing response time and improving user experience.

---

## Quick Start Guide

1. **Sign Up and Login**: Register using Globus Auth to enable access.
2. **Select Access Tier**: Choose between **Free** or **Premium** access, each with unique privileges.
3. **Submit Genomic Data**: Use the intuitive UI to submit data for annotation.
4. **Receive Notifications**: Get real-time email notifications upon job completion.
5. **Access & Download Results**: Free users can retrieve archived data, while Premium users have direct download access.

---

## Project Structure

### ann/
This folder contains all files related to the **Annotation** service. It includes:
- `annotator.py`: The primary script responsible for processing genomic annotation jobs.
- `ann_config.ini`: Configuration file holding essential parameters like S3 bucket names, DynamoDB table names, and other service-related details.
- `run.py`: A helper script that initiates the annotation process based on user requests.

The annotation service manages job requests and coordinates with other components to handle different user access levels.

### aws/
This folder includes AWS configuration and automation files. Key files:
- `user_data_web_server.txt`: Contains initialization scripts to configure new EC2 instances for the web server.
- `user_data_annotator.txt`: Initialization scripts for annotation servers, including commands to set up necessary dependencies and launch the annotation process.

These files automate the setup and configuration of web and annotator instances, ensuring seamless scaling.

### util/
This folder contains utility scripts and configurations supporting background tasks. Key components:
- `archive.py`: Script that moves Free-tier users' completed jobs to **AWS Glacier** for long-term storage.
- `restore.py`, `thaw.py`: Scripts that manage the restoration of archived files for users who upgrade to Premium.
- Configuration files for each utility script, managing parameters and environment variables for secure data handling.

### web/
This folder houses the **web application** codebase, handling user interactions, authentication, and data management.
- `views.py`: The primary script containing route handlers for user actions like login, job submission, and download requests.
- `config.py`: Configuration file holding application-specific settings like database credentials, S3 bucket names, and SNS/SQS queue names.
- Templates (`/templates`): HTML templates for rendering the web interface, creating a consistent and user-friendly UI.

The `web` directory powers the user-facing part of the Genomic Annotation Service, coordinating with the backend for annotation tasks and notification handling.

# 