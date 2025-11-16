import os
import importlib
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
from streamlit_option_menu import option_menu

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent          # .../admin_portal
ROOT = BASE.parent                              # repo root (contains user_portal/)
sys.path.insert(0, str(BASE))                   # import admin_portal.api / page
sys.path.insert(0, str(ROOT))

# --- Load environment variables ---
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(supabase_url, supabase_key)


def render():
    """Entry point for the admin portal (called from login/app.py or directly)."""

    st.set_page_config(layout="wide")

    # --- Initialize session state ---
    if "current_page" not in st.session_state:
        st.session_state.current_page = "/page/admin_home"
    if "top_nav_selected" not in st.session_state:
        st.session_state.top_nav_selected = 0

    st.title("📊 Admin Dashboard")

    # --- Define pages and icons ---
    page_options = ["Admin Home", "User Home", "News", "Stock Analysis", "Watchlist","Insights"]
    page_paths = {
        "Admin Home": "/page/admin_home",
        "User Home": "/page/home",
        "News": "/page/news",
        "Stock Analysis": "/page/stock_analysis",
        "Watchlist": "/page/watchlist",
        "Insights": "/page/insights",
    }
    page_icons = ["house", "house", "newspaper", "bar-chart", "bookmark","pie-chart"]

    # --- Top navigation bar ---
    selected = option_menu(
        menu_title=None,
        options=page_options,
        icons=page_icons[: len(page_options)],
        menu_icon="cast",
        default_index=st.session_state.top_nav_selected,
        orientation="horizontal",
        key=f"top_nav_bar_{st.session_state.top_nav_selected}",
        styles={
            "container": {"padding": "0!important", "background-color": "#f0f2f6"},
            "nav-link": {
                "font-size": "16px",
                "text-align": "center",
                "margin": "0px",
                "--hover-color": "#eee",
            },
            "nav-link-selected": {"background-color": "#0d6efd", "color": "white"},
        },
    )

    # --- Handle navigation selection ---
    st.session_state.top_nav_selected = page_options.index(selected)
    st.session_state.current_page = page_paths[selected]

    # --- Dynamic page import ---
    page = st.session_state.current_page
    module_name = page.replace("/", ".")[1:]  # "/page/admin_home" -> "page.admin_home"

    try:
        if page.startswith("/page"):
            module = importlib.import_module(module_name)
            if hasattr(module, "page"):
                module.page(supabase=supabase)
            else:
                st.error(f"`{module_name}` loaded but missing `page(**kwargs)`.")            
        else:
            st.error(f"Unknown page root for '{page}'. Expected '/page/*'.")
    except ModuleNotFoundError:
        st.error(f"Page module '{module_name}' not found.")
    except Exception as e:
        st.error(f"Failed to render '{module_name}': {e}")


# --- Allow running directly with: streamlit run admin_portal/app.py ---
if __name__ == "__main__":
    render()
