# app.py
import streamlit as st
from supabase import create_client
from dotenv import load_dotenv
import os
import importlib
from streamlit_option_menu import option_menu

# --- Load environment variables ---
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(supabase_url, supabase_key)

st.set_page_config(layout="wide")

# --- Helper functions ---
def safe_rerun():
    """Rerun the app safely"""
    try:
        if hasattr(st, "rerun"):
            return st.rerun()
    except:
        st.stop()

def sign_in(email, password):
    try:
        return supabase.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        st.error(f"Login failed: {e}")
        return None

def sign_out():
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state.user_session = None
    st.session_state.current_page = None
    st.session_state.top_nav_selected = 0
    st.query_params = {}  # remove token
    safe_rerun()

def sign_up(email, password):
    try:
        res = supabase.auth.sign_up({"email": email, "password": password})
        if res.user:
            st.success("Signup successful! Please login.")
        else:
            st.warning("Signup may require email confirmation.")
    except Exception as e:
        st.error(f"Signup failed: {e}")

# --- Initialize session state ---
if "user_session" not in st.session_state:
    st.session_state.user_session = None
if "current_page" not in st.session_state:
    st.session_state.current_page = None
if "top_nav_selected" not in st.session_state:
    st.session_state.top_nav_selected = 0

# --- Try restoring session from query params ---
if st.session_state.user_session is None:
    token = st.query_params.get("token")
    if token:
        try:
            user_data = supabase.auth.get_user(token[0])
            st.session_state.user_session = user_data.user
        except:
            st.session_state.user_session = None

# --- Login / Signup ---
if not st.session_state.user_session:
    tab_login, tab_signup = st.tabs(["Login", "Signup"])

    with tab_login:
        st.subheader("🔐 Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", key="login_btn"):
            res = sign_in(email, password)
            if res:
                st.session_state.user_session = res
                role = res.user.app_metadata.get("role", "user")
                st.session_state.current_page = "/admin/home" if role=="admin" else "/user/home"
                st.session_state.top_nav_selected = 0
                # Persist token in query params
                st.query_params = {"token": res.session.access_token}
                safe_rerun()

    with tab_signup:
        st.subheader("📝 Signup")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Signup", key="signup_btn"):
            sign_up(new_email, new_password)

# --- Main app after login ---
else:
    try:
        role = st.session_state.user_session.user.app_metadata.get("role", "user")
    except:
        role = "user"

    st.title("📊 My Dashboard")

    # --- Define pages and icons ---
    if role == "admin":
        page_options = ["Admin Home", "User Home", "News", "Stock Analysis", "Watchlist", "Logout"]
        page_paths = {
            "Admin Home": "/admin/home",
            "User Home": "/user/home",
            "News": "/user/news",
            "Stock Analysis": "/user/stock_analysis",
            "Watchlist": "/user/watchlist",
            "Logout": "logout"
        }
        page_icons = ["gear", "house", "newspaper", "bar-chart", "bookmark", "box-arrow-right"]
    else:
        page_options = ["User Home", "News", "Stock Analysis", "Watchlist", "Logout"]
        page_paths = {
            "User Home": "/user/home",
            "News": "/user/news",
            "Stock Analysis": "/user/stock_analysis",
            "Watchlist": "/user/watchlist",
            "Logout": "logout"
        }
        page_icons = ["house", "newspaper", "bar-chart", "bookmark", "box-arrow-right"]

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
    current_page = page_paths[selected]

    if current_page == "logout":
        sign_out()
    else:
        st.session_state.current_page = current_page

        # --- Dynamic page import ---
        page = st.session_state.current_page
        try:
            if page.startswith("/admin"):
                module = importlib.import_module("views.admin.home")
                module.admin_home(session=st.session_state.user_session, supabase=supabase)
            elif page.startswith("/user"):
                module_name = page.replace("/", ".")[1:]  # "/user/news" -> "views.user.news"
                module_name = f"views.{module_name}"
                module = importlib.import_module(module_name)
                if hasattr(module, "user_page"):
                    module.user_page(session=st.session_state.user_session, supabase=supabase)
                else:
                    st.error("Page function not found.")
        except ModuleNotFoundError:
            st.error(f"Page module {module_name} not found.")
