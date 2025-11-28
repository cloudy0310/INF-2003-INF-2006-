# INF-2003-INF-2006-
Cloud project (stocks website)
*Cloud-Deployed Python + PostgreSQL Application on AWS*

---

## Live Deployment (Public)
http://13.222.119.68

This endpoint is publicly hosted on AWS and served via the infrastructure provisioned through CloudFormation.

---

## Overview

This project is a cloud-deployed stocks analytics platform 
It includes:

- A **User Portal** for viewing stocks data  
- An **Admin Portal** for managing stocks and users  
- A **Python backend** that exposes all application logic  
- A **PostgreSQL database** for persistent storage  
- **AWS-hosted deployment** using CloudFormation for full Infrastructure-as-Code (IaC)

The system demonstrates database design, backend architecture, cloud deployment, automation scripts, and infrastructure provisioning.

---

## Repository Structure

/admin_portal Frontend for admin users
/user_portal Frontend for normal users
/pipeline_scripts Automation & deployment scripts
/CloudFormation.yaml AWS IaC template for provisioning
/requirements.txt Python backend dependencies
/.env.example Template for required environment variables

---

## Architecture

### Backend
- Python (Flask / FastAPI)
- REST API for frontend portals
- Connected to AWS-hosted PostgreSQL

### Database
- Amazon RDS PostgreSQL  
- PL/pgSQL stored functions & triggers  
- Tables for users, stocks, audit logs, etc.

### **Infrastructure (AWS)**
Provisioned using `CloudFormation.yaml`:

- VPC, subnets, route tables  
- EC2 instance for backend hosting  
- RDS PostgreSQL instance  
- Security groups  
- IAM roles  
- S3 bucket for static assets  

---

## Prerequisites

Before running locally or deploying:

- Python **3.9+**  
- PostgreSQL client tools  
- AWS CLI configured (`aws configure`)  
- IAM permissions to deploy CloudFormation stacks  
- Git  

---
## Deployment
(to be added on how to deploy)

---
## Environment Variables

Copy `.env.example` → `.env`:

```bash
cp .env.example .env
Fill in values:

ini
Copy code
DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=

SECRET_KEY=
JWT_SECRET=
CLOUD_REGION=ap-southeast-1

---




