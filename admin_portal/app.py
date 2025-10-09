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

# Reference the external CSS file
st.markdown(
    """
    <style>
        /* Background Color */
        body {
            background-color: #f4f4f9;
        }

        /* Title Styling */
        .css-1f4nmg3 {
            font-family: 'Roboto', sans-serif;
            font-weight: 600;
            color: #333;
            font-size: 28px;
        }

        /* Button Styling */
        .stButton > button {
            background-color: #0077b6;
            color: white;
            border-radius: 5px;
            font-size: 16px;
            padding: 0.5rem 1rem;
            transition: background-color 0.3s ease;
        }

        .stButton > button:hover {
            background-color: #00b4d8;
        }

        /* Input Styling */
        .stTextInput input {
            font-size: 14px;
            padding: 0.5rem;
            border-radius: 5px;
        }

        .stSelectbox, .stTextArea {
            font-size: 14px;
            border-radius: 5px;
        }

        .stCheckbox {
            font-size: 14px;
        }

        /* Sidebar Styling */
        .css-1d391kg {
            background-color: #f0f0f0;
        }

        .badge {
            background: #eef2ff;
            border: 1px solid #dbeafe;
            color: #1e40af;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 12px;
            margin-right: 6px;
        }

        .row-hr {
            border: none;
            border-bottom: 1px solid #eee;
            margin: 0.35rem 0;
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
