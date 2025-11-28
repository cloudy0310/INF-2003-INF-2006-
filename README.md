# INF-2003 & INF-2006 Cloud + Big Data Project  
### Cloud-Deployed Stocks Analytics Platform (Python + PostgreSQL + AWS)

## 🚀 Live Deployment  
http://13.222.119.68  
Publicly hosted on AWS EC2 with full Infrastructure-as-Code provisioning.

---

# 📌 1. Overview

This project is a **cloud-native stocks analytics platform** developed for:

- **INF2003 – Database Systems**
- **INF2006 – Cloud Computing & Big Data**

It integrates:

- Python backend (REST API)  
- PostgreSQL relational database with PL/pgSQL functions  
- Streamlit web portals (User + Admin)  
- AWS-hosted deployment using CloudFormation  
- Big data ingestion + ETL using S3, Lambda, Glue, EMR  

The system provides:

- **User Portal** for analytics, signals, summaries  
- **Admin Portal** for data management  
- **Big Data Pipeline** for automated processing  
- **Cloud Infrastructure** for scalability and automation  

---

# 📁 2. Repository Structure

/admin_portal – Admin dashboard (Streamlit)
/user_portal – User dashboard (Streamlit)
/backend – Python REST API backend
/pipeline_scripts – Lambda, Glue, EMR jobs
/docs – Architecture diagrams, screenshots
/CloudFormation.yaml – Full IaC template
/requirements.txt – Python libraries
/.env.example – Environment variable template

yaml
Copy code

---

# ☁️ 3. Cloud Architecture (High-Level)

### Compute
- EC2 instance hosting backend & portals  
- Lambda for automated ingestion  

### Storage
- Amazon RDS PostgreSQL  
- Amazon S3 Data Lake (raw + processed parquet)

### Big Data
- AWS Glue ETL (daily technical indicators)  
- Amazon EMR for heavy NLP (LLM news summarization + sentiment)

### IaC
Provisioned using CloudFormation:

- VPC, subnets, routing tables  
- EC2 instance  
- RDS PostgreSQL  
- IAM roles  
- Security groups  
- S3 buckets  
- Glue + EMR roles  

---

# 🧠 4. Big Data Pipeline (INF2006 Component)

## 4.1 Data Ingestion (Lambda)

### Stock Prices (5 min)
- Fetch prices via yfinance  
- Convert to Parquet  
- Store in:  
  `s3://data-lake/raw/stocks/YYYY-MM-DD/`

### News Articles (30 min)
- Fetch articles  
- Store JSON in:  
  `s3://data-lake/raw/news/`

---

## 4.2 ETL Processing

### AWS Glue – Daily Batch Processing
Performs distributed Spark computations:

- RSI  
- MACD  
- Bollinger Bands  
- SMA / EMA  
- Cleans OHLC data  

Output written to:  
`s3://data-lake/processed/stocks/`

---

## 4.3 AWS EMR – NLP / LLM Processing

Handles workloads too large for Glue:

- Sentiment analysis  
- Topic clustering  
- Extractive + abstractive summaries  
- Batch LLM processing  

Output written to:  
`s3://data-lake/processed/news/`

---

## 4.4 Output Delivery
Processed results are stored in:

- PostgreSQL (metadata + summaries)  
- DynamoDB (signals, if enabled)  

Served to frontends with sub-second latency.

---

# 🛠 5. Running Locally

## Install dependencies
```bash
pip install -r requirements.txt
Run backend
bash
Copy code
cd backend
python app.py
Run User Portal
bash
Copy code
cd user_portal
streamlit run app.py
Run Admin Portal
bash
Copy code
cd admin_portal
streamlit run app.py
🔧 6. Deployment (CloudFormation)
Deploy stack
bash
Copy code
aws cloudformation deploy \
  --template-file CloudFormation.yaml \
  --stack-name stocks-app \
  --capabilities CAPABILITY_NAMED_IAM
SSH into EC2
bash
Copy code
ssh -i key.pem ec2-user@<public-ip>
🔐 7. Environment Variables
Copy .env.example → .env and fill in:

env
Copy code
DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=

SECRET_KEY=
JWT_SECRET=
CLOUD_REGION=ap-southeast-1
