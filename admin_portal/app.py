import os
import importlib
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

# Load environment variables
load_dotenv()
st.set_page_config(layout="wide")

# Create RDS engine for SQLAlchemy
@st.cache_resource(show_spinner=False)
def get_rds_engine() -> Engine:
    host = os.getenv("RDS_HOST")
    port = int(os.getenv("RDS_PORT", "5432"))
    db = os.getenv("RDS_DB")
    user = os.getenv("RDS_USER")
    pwd = os.getenv("RDS_PASSWORD")
    if not all([host, db, user, pwd]):
        raise RuntimeError("Missing one of RDS_HOST, RDS_DB, RDS_USER, RDS_PASSWORD.")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}?sslmode=require"
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, future=True)

# Store RDS engine in session state
if "rds_engine" not in st.session_state:
    st.session_state.rds_engine = get_rds_engine()

DB_SCHEMA = os.getenv("DB_SCHEMA", "public").strip()

# Set search path for PostgreSQL schema
@event.listens_for(st.session_state.rds_engine, "connect")
def set_search_path(dbapi_connection, connection_record):
    with dbapi_connection.cursor() as cur:
        cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

# Inject gradient background CSS
st.markdown(
    """
    <style>
    /* Gradient background for full page */
    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* Card-like content areas */
    .block-container {
        background: rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem 3rem;
        margin: 2rem auto;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    }

    /* Optional: make headings bold & stylish */
    h1, h2, h3 {
        font-weight: 700;
        color: #0f172a;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Admin Home Page
st.title("📊 My Dashboard")

page_options = ["Admin Home", "User Home", "News", "Stock Analysis", "Watchlist", "Insights"]
page_paths = {
    "Admin Home": "/page/admin_home",
    "User Home": "/page/home",
    "News": "/page/news",
    "Stock Analysis": "/page/stock_analysis",
    "Watchlist": "/page/watchlist",
    "Insights": "/page/insights",
}

# Add navigation
from streamlit_option_menu import option_menu
selected = option_menu(
    menu_title=None,
    options=page_options,
    icons=["house", "newspaper", "bar-chart", "bookmark", "pie-chart", "pie-chart"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
)

# Dynamically load the selected page
page = page_paths[selected]
module_name = page.replace("/", ".")[1:]

try:
    module = importlib.import_module(module_name)
    if hasattr(module, "page"):
        module.page(rds=st.session_state.rds_engine)
except Exception as e:
    st.error(f"Error: {e}")
