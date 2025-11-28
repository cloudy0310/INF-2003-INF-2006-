# Stock Analytics Platform 📊
_A Big Data & AI-Driven Stock Insights Dashboard_

This project is an end-to-end cloud-native financial analytics system built using **AWS**, **distributed Spark processing**, and **LLM-driven summarisation**. It integrates multi-source financial data, computes technical indicators at scale, summarises market news using generative AI, and delivers personalised insights through a user-friendly dashboard.

**Trading Signals:**

<img width="1692" height="769" alt="Screenshot 2025-11-28 211543" src="https://github.com/user-attachments/assets/ef45404b-3d01-4975-84dd-bdd680f30b91" />

**Watchlist-Portfolio Analysis:**

<img width="1712" height="812" alt="Screenshot 2025-11-28 211620" src="https://github.com/user-attachments/assets/ab8f0282-95c1-4bb2-b62b-7fbbf0410afb" />

**AI-Powered News Insights:**

![6145251319384575233](https://github.com/user-attachments/assets/d1fba581-fde5-4303-bc81-0d21a8c04a99)
![6145251319384575240](https://github.com/user-attachments/assets/f1ad3231-4710-47ad-bf96-156560afe7a1)


## What This Project Does

This project is a full-stack stock analytics platform that provides:

- **User Portal**: Real-time stock analysis, portfolio tracking, financial news feeds, watchlist management, and market insights
- **Admin Portal**: User management, content administration, system analytics, and platform monitoring
- **Automated Data Pipeline**: Scheduled ETL jobs for stock prices, company information, financial data, and news articles
- **Cloud-Native Architecture**: Production-ready AWS infrastructure with auto-scaling, load balancing, and high availability

The platform uses AWS Cognito for secure authentication with role-based access control (admin/user groups).

## Why This Project is Useful

- **End-to-End Solution**: Complete platform for stock analysis and portfolio management without building from scratch
- **Scalable Infrastructure**: AWS CloudFormation templates enable one-click deployment with auto-scaling EC2 instances
- **Real-Time Data**: Automated Lambda and Glue jobs continuously fetch and process market data
- **Production-Ready**: Includes load balancing, multi-AZ deployment, and database replication
- **Extensible Design**: Modular portal structure makes it easy to add new features and pages
- **Secure Authentication**: AWS Cognito integration with OAuth2, token refresh, and group-based authorization

## Getting Started

### Prerequisites

- **Python 3.9+**
- **pip** (Python package manager)
- **PostgreSQL** (local or AWS RDS)
- **AWS Account** (for deployment)
- **AWS CLI** (configured for deployment)
- **Git**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/cloudy0310/INF-2003-INF-2006-.git
   cd INF-2003-INF-2006-
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create and configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your configuration:
   ```ini
   # AWS Cognito
   COGNITO_DOMAIN=your-domain.auth.region.amazoncognito.com
   COGNITO_CLIENT_ID=your_client_id
   COGNITO_CLIENT_SECRET=your_client_secret
   COGNITO_REDIRECT_URI=http://localhost:8501

   # Database
   RDS_HOST=your-rds-endpoint.region.rds.amazonaws.com
   RDS_PORT=5432
   RDS_DB=stock_db
   RDS_USER=postgres
   RDS_PASSWORD=your_password
   DB_SCHEMA=public

   # AWS
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=your_access_key
   AWS_SECRET_ACCESS_KEY=your_secret_key
   ```

4. **Run the application**
   ```bash
   streamlit run app.py
   ```
   
   The application will be available at `http://localhost:8501`

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your Cognito and database credentials

# Run locally
streamlit run app.py

# Login using your Cognito credentials
# Users in the 'admin' group access admin portal
# Other users access user portal
```

## Project Structure

```
├── app.py                          # Main entry point (authentication & routing)
├── update_details.py               # User profile management
├── requirements.txt                # Python dependencies
├── CloudFormation.yaml             # AWS infrastructure template
│
├── admin_portal/                   # Admin dashboard
│   ├── app.py                      # Admin portal router
│   ├── styles.css                  # Custom styling
│   ├── api/                        # API endpoints
│   │   ├── admin_content.py
│   │   ├── stock_analysis.py
│   │   ├── portfolio.py
│   │   ├── watchlist.py
│   │   └── display_news.py
│   └── page/                       # UI pages
│       ├── admin_home.py           # Admin dashboard
│       ├── stock_analysis.py
│       ├── watchlist.py
│       ├── news.py
│       └── insights.py
│
├── user_portal/                    # User dashboard
│   ├── app.py                      # User portal router
│   ├── db.py                       # Database utilities
│   ├── api/                        # API endpoints
│   │   ├── stock_analysis.py
│   │   ├── portfolio.py
│   │   ├── watchlist.py
│   │   └── display_news.py
│   └── page/                       # UI pages
│       ├── home.py                 # Dashboard
│       ├── stock_analysis.py
│       ├── watchlist.py
│       ├── news.py
│       ├── insights.py
│       └── update_details.py
│
└── pipeline_scripts/               # Data processing
    ├── infra/                      # SQL setup scripts
    │   ├── set-up.sql
    │   └── rds.sql
    └── pipeline (Big Data)/        # Current ETL pipeline
        ├── fetch_companies.py
        ├── fetch_financials.py
        ├── fetch_news_daily.py
        ├── stock-price-to-s3-lambda.py
        ├── spark_summarize_articles.py
        └── utils.py
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Streamlit, Plotly, Custom CSS |
| **Backend** | Python, SQLAlchemy, PostgreSQL |
| **Cloud** | AWS (EC2, ALB, RDS, Lambda, DynamoDB, Cognito) |
| **Data Processing** | AWS Glue, Apache Spark, Pandas |
| **Infrastructure** | CloudFormation, Auto Scaling Groups |
| **Authentication** | AWS Cognito (OAuth2/OIDC) |

## Usage Examples

### For Users

**View Portfolio Dashboard**
- Login with your Cognito account
- Navigate to "User Portal" → "Home"
- View holdings, performance, and watchlist

**Analyze a Stock**
- Go to "Stock Analysis"
- Enter a stock ticker (e.g., AAPL, GOOGL)
- Review technical analysis and metrics

**Read Financial News**
- Navigate to "News" section
- Filter by category or date
- Read summarized news articles

### For Admins

**Access Admin Dashboard**
- Login with admin group credentials
- Navigate to "Admin Portal"
- View analytics and system metrics

**Manage Content**
- Go to "Content Management"
- Review and curate news articles
- Update stock data

## Deployment

### Deploy to AWS

1. **Create an EC2 key pair**
   ```bash
   aws ec2 create-key-pair --key-name stock-app-key
   ```

2. **Prepare Cognito**
   - Create a Cognito User Pool
   - Add app client with Cognito-hosted UI
   - Create admin user group

3. **Deploy CloudFormation stack**
   ```bash
   aws cloudformation create-stack \
     --stack-name stock-app \
     --template-body file://CloudFormation.yaml \
     --parameters \
       ParameterKey=KeyPairName,ParameterValue=stock-app-key \
       ParameterKey=DBUser,ParameterValue=postgres \
       ParameterKey=DBPassword,ParameterValue=YourSecurePassword123!
   ```

4. **Monitor stack creation**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name stock-app \
     --query 'Stacks[0].StackStatus'
   ```

5. **Get the application URL**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name stock-app \
     --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
     --output text
   ```

### Infrastructure Components

- **VPC & Networking**: Multi-AZ setup with public/private subnets
- **EC2 Auto Scaling**: 2-4 instances running Streamlit app
- **Application Load Balancer**: Distributes traffic across instances
- **RDS PostgreSQL**: 20GB database for user and stock data
- **DynamoDB**: NoSQL table for news storage
- **Lambda Functions**: Scheduled jobs for data updates
- **Cognito User Pool**: Manages authentication and authorization

## Data Pipeline

The platform includes automated data collection and processing:

### Stock Prices
- Lambda function runs daily (via CloudWatch Events)
- Fetches latest prices using yfinance API
- Stores in PostgreSQL RDS

### Company & Financial Data
- Weekly fetch of company information
- Officer details and corporate structure
- Financial metrics and ratios

### News Processing
- Real-time and daily news scraping
- AWS Glue + Spark jobs for article summarization
- Stores in DynamoDB with metadata

### Analytics
- Batch processing for insights
- Performance calculations
- Trend analysis

## Where to Get Help

### Documentation
- **Setup**: See `.env.example` for all configuration options
- **Infrastructure**: Review `CloudFormation.yaml` for AWS architecture details
- **Data Pipeline**: Check `pipeline_scripts/` directory for ETL jobs
- **Portal Code**: Each portal's `app.py` contains routing logic

### Resources
- [Streamlit Documentation](https://docs.streamlit.io/)
- [AWS CloudFormation Guide](https://docs.aws.amazon.com/cloudformation/)
- [AWS Cognito Setup](https://docs.aws.amazon.com/cognito/latest/developerguide/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)

### Troubleshooting

**Database Connection Failed**
- Verify RDS endpoint and credentials in `.env`
- Check security group allows port 5432 from your IP
- Ensure database schema exists

**Cognito Login Not Working**
- Confirm COGNITO_DOMAIN, CLIENT_ID in `.env`
- Verify redirect URI matches app URL in Cognito console
- Check user exists in Cognito User Pool

**Module Import Errors**
- Ensure running `streamlit run app.py` from project root
- Verify all dependencies installed: `pip install -r requirements.txt`
- Check `sys.path` configuration in portal `app.py` files

## 👥 Contributors

| Name            | Role                                         |
|-----------------|----------------------------------------------|
| Leong Wei Jie   | News Pipeline, EMR NLP, Gemini Integration   |
| Li Yiming       | AWS Architecture, Dashboard, RDS/DynamoDB    |
| Teo Shao Xuan   | Session & Cookie Management                  |
| Claudia Yue     | Cognito Authentication                       |
| Lee Yun Jia     | Company Data & Dashboard Analytics           |

## 🛠 Future Work

- **Spark Structured Streaming** for near real-time indicator computation  
- **LLM-powered sentiment classification** to complement summarisation  
- **Reinforcement-learning trading agents** for long-horizon strategy simulation  
- **Full API Gateway + Lambda microservice architecture** for cleaner API boundaries  
- **Factor-based portfolio optimisation** and advanced quant analytics  
- **Dedicated mobile app** with push notifications for news summaries & alerts  
- **User journey analytics** to drive personalised recommendation ranking  


## 📄 License

This project is licensed under the **MIT License**.


---

**Happy investing! 📈**
