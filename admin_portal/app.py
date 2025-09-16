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

# --- Define pages and icons (add Admin) ---
page_options = ["User Home", "News", "Stock Analysis", "Watchlist", "Admin"]
page_paths = {
    "User Home": "/user_page/home",
    "News": "/user_page/news",
    "Stock Analysis": "/user_page/stock_analysis",
    "Watchlist": "/user_page/watchlist",
    "Admin": "/admin_page/home",
}
page_icons = ["house", "newspaper", "bar-chart", "bookmark", "gear"]

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
route = page.replace("/", ".")[1:]  # "/user_page/news" -> "user_page.news"

try:
    module = None

    if page.startswith("/user_page"):
        # e.g. user_page.home
        module = importlib.import_module(route)
        if hasattr(module, "user_page"):
            module.user_page(supabase=supabase)
        else:
            st.error(f"`{route}` loaded but missing `user_page(**kwargs)`.")

    elif page.startswith("/admin_page"):
        # Try plain 'admin_page.home' first, then 'admin_portal.admin_page.home' (matches your folder structure)
        try:
            module = importlib.import_module(route)  # admin_page.home
        except ModuleNotFoundError:
            module = importlib.import_module(f"admin_portal.{route}")  # admin_portal.admin_page.home

        # Prefer admin_page(), fallback to admin_home()
        if hasattr(module, "admin_page"):
            module.admin_page(supabase=supabase)
        elif hasattr(module, "admin_home"):
            module.admin_home(supabase=supabase)
        else:
            st.error(f"`{module.__name__}` loaded but missing `admin_page(**kwargs)` or `admin_home(**kwargs)`.")

    else:
        st.error(f"Unknown page root for '{page}'. Expected '/user_page/*' or '/admin_page/*'.")

except ModuleNotFoundError:
    st.error(f"Page module '{route}' not found (also tried 'admin_portal.{route}' for admin pages).")
except Exception as e:
    st.error(f"Failed to render page '{route}': {e}")
