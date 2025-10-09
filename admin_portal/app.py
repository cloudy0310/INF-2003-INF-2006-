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

# ------------------------------
# ✨ Custom CSS Styling
# ------------------------------
st.markdown(
    """
    <style>
    /* ===== Base Page Setup ===== */
    .stApp {
        background: #ffffff; /* Default background for non-header sections */
        font-family: 'Inter', sans-serif;
        color: #0f172a;
    }

    /* ===== Gradient Header (Dashboard section) ===== */
    .dashboard-header {
        background: linear-gradient(135deg, #dbeafe, #93c5fd, #1e3a8a);
        padding: 2.5rem 2rem;
        border-radius: 16px;
        color: white;
        box-shadow: 0 4px 25px rgba(0, 0, 0, 0.1);
        margin-bottom: 2rem;
    }

    .dashboard-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 800;
        color: white;
    }

    /* ===== White Content Area ===== */
    .block-container {
        background: #ffffff;
        border-radius: 16px;
        padding: 2rem 3rem;
        box-shadow: 0 4px 25px rgba(0, 0, 0, 0.05);
    }

    /* ===== Orange Table Section ===== */
    .orange-section {
        background: linear-gradient(135deg, #fef3c7, #fcd34d, #f59e0b);
        padding: 1.5rem;
        border-radius: 12px;
        margin: 1rem 0;
        color: #78350f;
        box-shadow: 0 2px 10px rgba(249, 115, 22, 0.2);
    }

    /* ===== Headings ===== */
    h1, h2, h3 {
        font-weight: 700;
    }

    /* ===== Option Menu Styling ===== */
    .nav-container {
        text-align: center;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# ------------------------------
# ✨ Dashboard Header Section
# ------------------------------
st.markdown(
    """
    <div class="dashboard-header">
        <h1>📊 My Dashboard</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# ------------------------------
# 🧭 Navigation Menu
# ------------------------------
page_options = ["Admin Home", "User Home", "News", "Stock Analysis", "Watchlist", "Insights"]
page_paths = {
    "Admin Home": "/page/admin_home",
    "User Home": "/page/home",
    "News": "/page/news",
    "Stock Analysis": "/page/stock_analysis",
    "Watchlist": "/page/watchlist",
    "Insights": "/page/insights",
}

selected = option_menu(
    menu_title=None,
    options=page_options,
    icons=["house", "newspaper", "bar-chart", "bookmark", "pie-chart", "lightbulb"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
)

# ------------------------------
# 🧩 Page Content Wrapper
# ------------------------------
st.markdown("<div class='block-container'>", unsafe_allow_html=True)

# Example orange table block (you can style your tables this way)
st.markdown("<div class='orange-section'>", unsafe_allow_html=True)
st.subheader("📋 Content Table Example")
st.write("This area highlights your table or important content section.")
st.markdown("</div>", unsafe_allow_html=True)

# Dynamic page loading
page = page_paths[selected]
module_name = page.replace("/", ".")[1:]

try:
    module = importlib.import_module(module_name)
    if hasattr(module, "page"):
        module.page(rds=st.session_state.rds_engine)
except Exception as e:
    st.error(f"Error: {e}")

st.markdown("</div>", unsafe_allow_html=True)

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
