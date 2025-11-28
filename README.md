# 📈 Cloud-Native Financial Analytics Platform  
### A Big Data & AI-Driven Stock Insights Dashboard

This project is an end-to-end cloud-native financial analytics system built using AWS, distributed Spark processing, and LLM-driven summarisation. It integrates multi-source financial data, computes technical indicators at scale, summarises market news using generative AI, and delivers personalised insights through a user-friendly dashboard.

---

# 🚀 Key Features

## **1. Automated Data Ingestion (Event-Driven)**  
- Stock prices collected daily via **AWS Lambda + EventBridge**  
- Financial news scraped via **Google News RSS feeds**  
- Canonical URL resolution + full-text extraction  
- All raw data stored in **Amazon S3 Data Lake**

---

## **2. Distributed Big Data Processing**

### **AWS Glue (Spark ETL)**
- Preprocess OHLC datasets  
- Compute technical indicators:  
  - MACD, RSI, EMA, SMA, Bollinger Bands  
- Generate buy/sell signals  
- Write derived analytics to **DynamoDB** for low-latency queries  

### **AWS EMR (Spark NLP + LLM)**
- Large-scale news cleaning & preparation  
- Prompted summarisation using **Google Gemini 2.5 Flash**  
- Daily narrative summaries written to **S3**

---

## **3. Hybrid Storage Architecture**

- **Amazon S3** → Data Lake for raw + processed datasets  
- **Amazon DynamoDB** → Time-series indicators & AI summaries  
- **Amazon RDS (PostgreSQL)** → Users, watchlists, metadata  

---

## **4. Secure User Access & Authentication**

- Managed authentication via **AWS Cognito**  
- JWT-based verification  
- Role-based access control (**Admin/User**)  

---

## **5. Interactive Streamlit Dashboard**

Hosted on **AWS EC2**, displaying:

- Real-time stock charts  
- Technical indicators  
- Buy/sell signals  
- Watchlist analytics  
- AI-generated market summaries  

Clean, responsive UI designed for beginner and intermediate investors.

---

# 🧱 System Architecture

### **High-Level Overview**
- **Ingestion Layer:** Lambda + EventBridge  
- **Storage Layer:** S3, RDS, DynamoDB  
- **Analytics Layer:** Glue Spark ETL + EMR Spark NLP  
- **Interface Layer:** EC2-hosted Streamlit dashboard  
- **Security Layer:** IAM, VPC, KMS, Cognito  

*(Insert architecture diagram)*  

---

# 📂 Project Structure

├── lambda/
│ ├── scrape_prices/
│ ├── scrape_news/
│
├── glue/
│ ├── preprocess_time_series.py
│ ├── compute_indicators.py
│
├── emr/
│ ├── news_nlp_pipeline.py
│
├── streamlit/
│ ├── pages/
│ ├── authentication/
│ ├── dashboard/
│
├── infrastructure/
│ ├── cloudformation/
│
├── docs/
│ ├── architecture_diagram.png
│ ├── data_flow.png
│
└── README.md

---

# ⚙️ Deployment Instructions

## **Prerequisites**
- AWS Account  
- IAM admin permissions  
- Python 3.10+  
- AWS CLI configured  
- Streamlit installed  
- Access to Gemini API  

---

## **1. Deploy Infrastructure (CloudFormation)**

```bash
aws cloudformation deploy \
  --template-file infra/template.yaml \
  --stack-name fin-analytics \
  --capabilities CAPABILITY_NAMED_IAM
2. Deploy Lambda Functions

cd lambda/scrape_prices
zip -r function.zip .

aws lambda update-function-code \
  --function-name scrapePrices \
  --zip-file fileb://function.zip
Repeat for the news ingestion function.

3. Start Glue Jobs

aws glue start-job-run \
  --job-name compute-indicators-job
4. Launch EMR Cluster for NLP

aws emr create-cluster \
  --name "Financial News NLP" \
  --release-label emr-6.13.0 \
  --applications Name=Spark \
  --instance-type m5.xlarge \
  --instance-count 3
5. Run Streamlit Dashboard

streamlit run dashboard/home.py
🔐 Security
The system implements multi-layer security:

VPC isolation for RDS/DynamoDB

IAM least-privilege roles per Lambda / Glue job

KMS encryption at rest

TLS 1.2+ encryption in transit

Cognito-managed authentication

Secrets stored in AWS Secrets Manager

📊 Experimental Results
Task	Lambda Time	Spark Time	Speedup
RSI (10k rows)	4.1s	0.7s	6×
MACD	6.5s	0.9s	7.2×
Bollinger Bands	3.8s	0.5s	7.6×

⚠ Limitations
Google News RSS provides inconsistent metadata

External LLM API introduces latency + rate-limit risks

EMR cluster spin-up overhead for small jobs

No API Gateway layer (currently uses direct SDK calls)

Limited RDS retention & governance policies

🛠 Future Work
Spark Structured Streaming for near real-time indicators

LLM sentiment classification

Reinforcement-learning trading agents

Full API Gateway microservice architecture

Factor-based portfolio optimisation

Mobile app with push notifications

User journey analytics for summarisation ranking

👥 Contributors
Name	Role
Leong Wei Jie	News Pipeline, EMR NLP, Gemini Integration
Li Yiming	Cloud Architecture, Dashboard, RDS/DynamoDB Integration
Teo Shao Xuan	Session & Cookie Management
Claudia Yue	Cognito Authentication
Lee Yun Jia	Company Data Retrieval & Analytics

