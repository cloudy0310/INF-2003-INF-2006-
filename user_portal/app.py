import os
import sys
import importlib
o
from dotenv import load_dotenv
from supabase import create_client
from streamlit_option_menu import option_menu
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# --- Load environment variables ---
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(supabase_url, supabase_key)

st.set_page_config(layout="wide")

# --- Initialize session state ---
if "current_page" not in st.session_state:
    st.session_state.current_page = "/page/home"
if "top_nav_selected" not in st.session_state:
    st.session_state.top_nav_selected = 0

st.title("📊 My Dashboard")

# --- Define pages and icons ---
page_options = ["User Home", "News", "Stock Analysis", "Watchlist", "Insights"]  # Add the new page here
page_paths = {
    "User Home": "/page/home",
    "News": "/page/news",
    "Stock Analysis": "/page/stock_analysis",
    "Watchlist": "/page/watchlist",
    "Insights": "/page/insight",  # Add path for the new page
}
page_icons = ["house", "newspaper", "bar-chart", "bookmark", "search"]  # Add an icon for the new page

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

# --- Navigation selection ---
st.session_state.top_nav_selected = page_options.index(selected)
st.session_state.current_page = page_paths[selected]

page = st.session_state.current_page
module_name = page.replace("/", ".")[1:]

try:
    if page.startswith("/page"):
        module = importlib.import_module(module_name)
        if hasattr(module, "page"):
            module.page(supabase=supabase)
        else:
            st.error(f"`{module_name}` loaded but missing `page(**kwargs)`.")  # Handle error if no page function is found
    else:
        st.error(f"Unknown page root for '{page}'. Expected '/page/*'.")
except ModuleNotFoundError:
    st.error(f"Page module '{module_name}' not found.")  # Handle error if module is not found
except Exception as e:
    st.error(f"Failed to render '{module_name}': {e}")  # Handle other errors during page rendering
