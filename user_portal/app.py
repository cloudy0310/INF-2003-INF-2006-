import os
import importlib
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
from streamlit_option_menu import option_menu

# --- Load environment variables ---
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(supabase_url, supabase_key)

st.set_page_config(layout="wide")

# --- Initialize session state (no auth) ---
if "current_page" not in st.session_state:
    st.session_state.current_page = "/user_page/home"   # default to user_page package
if "top_nav_selected" not in st.session_state:
    st.session_state.top_nav_selected = 0

st.title("📊 My Dashboard")

# --- Define pages and icons (no admin, no logout) ---
page_options = ["User Home", "News", "Stock Analysis", "Watchlist"]
page_paths = {
    "User Home": "/user_page/home",
    "News": "/user_page/news",
    "Stock Analysis": "/user_page/stock_analysis",
    "Watchlist": "/user_page/watchlist",
}
page_icons = ["house", "newspaper", "bar-chart", "bookmark"]

# --- Top navigation bar ---
selected = option_menu(
    menu_title=None,
    options=page_options,
    icons=page_icons[:len(page_options)],
    menu_icon="cast",
    default_index=st.session_state.top_nav_selected,
    orientation="horizontal",
    key=f"top_nav_bar_{st.session_state.top_nav_selected}",
    styles={
        "container": {"padding": "0!important", "background-color": "#f0f2f6"},
        "nav-link": {"font-size": "16px", "text-align": "center", "margin": "0px", "--hover-color": "#eee"},
        "nav-link-selected": {"background-color": "#0d6efd", "color": "white"},
    }
)

# --- Handle navigation selection ---
st.session_state.top_nav_selected = page_options.index(selected)
st.session_state.current_page = page_paths[selected]

# --- Dynamic page import (no session/auth passed) ---
page = st.session_state.current_page
module_name = page.replace("/", ".")[1:]  # "/user_page/news" -> "user_page.news"

try:
    if page.startswith("/user_page"):
        module = importlib.import_module(module_name)
        # Expect a user_page() entrypoint with no auth args
        if hasattr(module, "user_page"):
            module.user_page(supabase=supabase)
        else:
            st.error(f"`{module_name}` loaded but missing `user_page(**kwargs)`.")
    else:
        st.error(f"Unknown page root for '{page}'. Expected '/user_page/*'.")
except ModuleNotFoundError:
    st.error(f"Page module '{module_name}' not found.")
except Exception as e:
    st.error(f"Failed to render '{module_name}': {e}")
