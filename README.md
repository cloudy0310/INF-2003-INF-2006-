# Stock Analytics Portal 📊

A full-stack stock analysis and portfolio management platform built with Streamlit and Supabase, featuring separate user and admin portals.

## What This Project Does

This is a web-based stock analytics platform that provides:

- **User Portal**: Track stock portfolios, analyze market data, view financial news, and manage watchlists
- **Admin Portal**: User management, content administration, and platform analytics
- **Automated Data Pipeline**: Scheduled ETL jobs that fetch stock prices, company data, and financial news
- **Real-time Updates**: Continuous data synchronization with financial data sources

The platform uses Supabase (PostgreSQL + Auth) for backend services and Streamlit for the frontend interface.

## Why This Project is Useful

- **Complete Solution**: End-to-end stock analysis platform without building from scratch
- **Multi-tenant Design**: Separate authenticated portals for regular users and administrators
- **Scalable Backend**: Supabase provides PostgreSQL database, real-time subscriptions, and authentication
- **Modular Architecture**: Easy to extend with new pages and API endpoints
- **Automated Data**: Background pipelines keep financial data fresh and up-to-date
- **Production-Ready**: Includes environment configuration, error handling, and user management

## Getting Started

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Supabase account and project
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/cloudy0310/INF-2003-INF-2006-.git
   cd INF-2003-INF-2006-
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your Supabase credentials:
   ```ini
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_ANON_KEY=your_anon_key_here
   SUPABASE_SERVICE_ROLE=your_service_role_key
   
   # Optional: Direct PostgreSQL connection
   PGHOST=db.your-project.supabase.co
   PGPORT=5432
   PGDATABASE=postgres
   PGUSER=postgres
   PGPASSWORD=your_password
   
   # Pipeline settings
   TICKERS=AAPL,MSFT,AMZN
   START=2010-01-01
   OUT_DIR=./data
   ```

5. **Run the application**
   ```bash
   streamlit run login/app.py
   ```
   
   The app will open at `http://localhost:8501`

### Quick Start Example

```bash
# 1. Setup virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

# 2. Install packages
pip install -r requirements.txt

# 3. Create .env with Supabase credentials
cp .env.example .env
# Edit .env with your values

# 4. Run the app
streamlit run login/app.py

# 5. Create a Supabase account and sign up
# Navigate to http://localhost:8501
# Sign up with email/password
# You'll be logged into your respective portal
```

## Project Structure

```
├── login/
│   ├── app.py                # Authentication & routing
│   └── supa.py              # Supabase client setup
├── admin_portal/
│   ├── app.py               # Admin dashboard router
│   ├── api/                 # Admin API functions
│   └── page/                # Admin pages (admin_home, insights, etc.)
├── user_portal/
│   ├── app.py               # User dashboard router
│   ├── api/                 # User API functions
│   └── page/                # User pages (home, stock_analysis, etc.)
├── pipeline_scripts/
│   ├── pipeline/            # ETL jobs
│   │   ├── fetch_companies.py
│   │   ├── fetch_financials.py
│   │   ├── fetch_news_daily.py
│   │   ├── fetch_stock_price_day.py
│   │   └── supabase_helpers.py
│   └── infra/               # Database setup scripts
├── terraform/               # Infrastructure as Code
├── requirements.txt         # Python dependencies
└── .env.example            # Configuration template
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Streamlit, Plotly, Pandas |
| Backend | Supabase (PostgreSQL) |
| Authentication | Supabase Auth |
| Data Pipeline | Python, yfinance |
| Data Storage | PostgreSQL (via Supabase) |

## Core Features

### User Portal
- Dashboard with portfolio overview
- Stock price analysis and technical indicators
- Financial news feed
- Personal watchlist
- User profile management

### Admin Portal
- User management and analytics
- Content administration
- System monitoring
- Insights dashboard

### Data Pipeline
- **Daily Stock Prices**: Fetches latest OHLCV data
- **Company Information**: Retrieves company details and officers
- **Financial Data**: Pulls quarterly/annual financials
- **News Feed**: Aggregates financial news articles

## Configuration

### Environment Variables

See `.env.example` for the complete template. Key variables:

- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_ANON_KEY`: Public Supabase key
- `SUPABASE_SERVICE_ROLE`: Service role key (for backend jobs)
- `PGHOST`, `PGUSER`, `PGPASSWORD`: Direct database connection (optional)
- `TICKERS`: Comma-separated stock symbols to track
- `START`: Historical data start date
- `OUT_DIR`: Local data output directory

## Deploying Data Pipeline

To run data fetch jobs:

```bash
cd pipeline_scripts/pipeline

# Fetch all historical stock data
python fetch_stock_price_all.py

# Fetch latest daily price
python fetch_stock_price_day.py

# Fetch company information
python fetch_companies.py

# Fetch financial data
python fetch_financials.py

# Fetch daily news
python fetch_news_daily.py
```

## Where to Get Help

### Documentation
- [Streamlit Docs](https://docs.streamlit.io/) - Framework documentation
- [Supabase Docs](https://supabase.com/docs) - Database and Auth setup
- [yfinance Docs](https://github.com/ranaroussi/yfinance) - Financial data source

### Common Issues

**Q: "Cannot connect to Supabase"**
- A: Verify `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `.env` match your project

**Q: "Login page not loading"**
- A: Ensure Supabase Auth is enabled in your project console

**Q: "Pipeline scripts fail"**
- A: Check that `SUPABASE_SERVICE_ROLE` is set and database tables are initialized

**Q: "Module import errors"**
- A: Make sure dependencies are installed: `pip install -r requirements.txt`

## Contributing

This project is developed for University of Saskatchewan coursework (INF-2003, INF-2006). 

For bug reports or feature requests, open an issue on GitHub.

## Project Information

- **Repository**: [INF-2003-INF-2006-](https://github.com/cloudy0310/INF-2003-INF-2006-)
- **Owner**: cloudy0310
- **Status**: Active Development
- **License**: See LICENSE file

---

**Happy analyzing! 📈**
