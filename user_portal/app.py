import os
import importlib
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from streamlit_option_menu import option_menu
import sys
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
try:
    import boto3
except Exception:
    boto3 = None

# --------------------------
# MAIN ENTRY FUNCTION
# --------------------------
def page():
    load_dotenv()
    st.set_page_config(layout="wide", page_title="User Portal")

    # --------------------------
    # Database connections
    # --------------------------
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

    if "rds_engine" not in st.session_state:
        st.session_state.rds_engine = get_rds_engine()

    DB_SCHEMA = os.getenv("DB_SCHEMA", "public").strip()

    @event.listens_for(st.session_state.rds_engine, "connect")
    def set_search_path(dbapi_connection, connection_record):
        with dbapi_connection.cursor() as cur:
            cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

    def _make_dynamo():
        if not boto3:
            return None
        region = os.getenv("AWS_REGION")
        if not region:
            return None
        return boto3.resource("dynamodb", region_name=region)

    if "dynamo" not in st.session_state:
        st.session_state.dynamo = _make_dynamo()

    # --------------------------
    # Top navigation
    # --------------------------
    st.title("📊 User Dashboard")

    page_options = ["User Home", "News", "Stock Analysis", "Watchlist", "Insights"]
    page_paths = {
        "User Home": "page.home",
        "News": "page.news",
        "Stock Analysis": "page.stock_analysis",
        "Watchlist": "page.watchlist",
        "Insights": "page.insights",
    }
    page_icons = ["house", "newspaper", "bar-chart", "bookmark", "pie-chart"]

    selected = option_menu(
        menu_title=None,
        options=page_options,
        icons=page_icons,
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "#f0f2f6"},
            "nav-link": {"font-size": "16px", "text-align": "center", "--hover-color": "#eee"},
            "nav-link-selected": {"background-color": "#0d6efd", "color": "white"},
        },
    )

    current_page = page_paths[selected]

    try:
        module = importlib.import_module(f"user_portal.{current_page}")
        if hasattr(module, "page"):
            module.page(
                rds=st.session_state.rds_engine,
                dynamo=st.session_state.dynamo,
            )
        else:
            st.error(f"Module {current_page} missing page(**kwargs).")
    except ModuleNotFoundError:
        st.error(f"Page module '{current_page}' not found.")
    except Exception as e:
        st.error(f"Failed to render '{current_page}': {e}")
