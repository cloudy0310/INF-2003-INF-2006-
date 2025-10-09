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

# --- Page Configuration ---
st.set_page_config(
    page_title="My Dashboard",
    page_icon="📊",
    layout="wide"
)

# --- Inject Custom CSS ---
st.markdown("""
    <style>
    /* Global page background */
    .stApp {
        background: linear-gradient(135deg, #dbeafe, #93c5fd, #1e3a8a);
        background-attachment: fixed;
        color: #0f172a;
        font-family: 'Inter', sans-serif;
    }

    /* Frosted glass card containers */
    .glass-card {
        background: rgba(255, 255, 255, 0.7);
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s ease-in-out;
    }

    .glass-card:hover {
        transform: translateY(-4px);
    }

    /* Center title */
    .main-title {
        text-align: center;
        color: #0f172a;
        font-weight: 800;
        font-size: 2.8rem;
        margin-top: 1rem;
        margin-bottom: 1rem;
    }

    /* Tabs / Buttons area */
    .nav-btn {
        background: rgba(255, 255, 255, 0.6);
        color: #0f172a;
        border-radius: 12px;
        padding: 0.6rem 1.2rem;
        margin-right: 0.6rem;
        border: none;
        cursor: pointer;
        font-weight: 500;
        transition: 0.3s;
    }

    .nav-btn:hover {
        background: rgba(255, 255, 255, 0.9);
    }

    /* Text styling */
    h3 {
        color: #1e293b;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }

    p {
        color: #334155;
        font-size: 1rem;
    }

    /* Button styling */
    .stButton>button {
        background-color: #2563eb;
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 1.2rem;
        font-weight: 600;
        transition: 0.2s;
    }

    .stButton>button:hover {
        background-color: #1d4ed8;
        transform: translateY(-2px);
    }

    </style>
""", unsafe_allow_html=True)

# --- Title ---
st.markdown("<h1 class='main-title'>📊 My Dashboard</h1>", unsafe_allow_html=True)

# --- Navigation Bar ---
st.markdown(
    """
    <div style='text-align:center; margin-bottom: 2rem;'>
        <button class='nav-btn'>🏠 Admin Home</button>
        <button class='nav-btn'>👤 User Home</button>
        <button class='nav-btn'>📰 News</button>
        <button class='nav-btn'>📈 Stock Analysis</button>
        <button class='nav-btn'>⭐ Watchlist</button>
        <button class='nav-btn'>💡 Insights</button>
    </div>
    """,
    unsafe_allow_html=True
)

# --- Layout Sections ---
col1, col2 = st.columns(2)

with col1:
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.subheader("🛠️ Admin — Content Manager")
    st.write("Create, edit, publish, and delete content shown on the user Home page.")
    st.button("+ Create new content")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.subheader("📅 Recent Updates")
    st.write("- Added new stock performance section\n- Fixed API response delay\n- Improved news feed rendering speed")
    st.markdown("</div>", unsafe_allow_html=True)

# --- Full-width Insights Section ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
st.subheader("📊 Analytics Overview")
st.write("""
Here’s where you can track performance and visualize data trends.
Future enhancements could include:
- Real-time stock metrics
- AI-generated investment insights
- Dynamic portfolio summaries
""")
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
