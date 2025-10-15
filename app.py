import streamlit as st
import os
import base64
import requests
from jose import jwt
from dotenv import load_dotenv
import importlib
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Load DB credentials
DB_HOST = os.getenv("RDS_HOST")
DB_PORT = os.getenv("RDS_PORT", "5432")
DB_NAME = os.getenv("RDS_DB")
DB_USER = os.getenv("RDS_USER")
DB_PASS = os.getenv("RDS_PASSWORD")

# Create engine
engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    echo=False
)
def sync_user_to_db(user_claims):
    """Insert or update a user record in PostgreSQL from Cognito claims."""
    try:
        with engine.begin() as conn:
            cognito_sub = user_claims.get("sub")
            email = user_claims.get("email")
            username = user_claims.get("cognito:username", email.split("@")[0] if email else "unknown")
            name = user_claims.get("name")
            is_admin = "admin" in user_claims.get("cognito:groups", [])

            # Check if user exists
            result = conn.execute(
                text("SELECT user_id FROM users WHERE cognito_sub = :sub"),
                {"sub": cognito_sub},
            ).fetchone()

            if result:
                # Update existing user (refresh name/email and last login)
                conn.execute(
                    text("""
                        UPDATE users 
                        SET 
                            email = :email,
                            name = COALESCE(:name, name),
                            last_login_at = NOW()
                        WHERE cognito_sub = :sub
                    """),
                    {"email": email, "name": name, "sub": cognito_sub},
                )
            else:
                # Insert new user
                conn.execute(
                    text("""
                        INSERT INTO users (
                            user_id, username, name, email, is_admin, 
                            created_at, last_login_at, cognito_sub
                        )
                        VALUES (
                            gen_random_uuid(), :username, :name, :email, :is_admin, 
                            NOW(), NOW(), :sub
                        )
                    """),
                    {
                        "username": username,
                        "name": name,
                        "email": email,
                        "is_admin": is_admin,
                        "sub": cognito_sub,
                    },
                )

    except SQLAlchemyError as e:
        st.error(f"Database error: {e}")


# Load environment variables
load_dotenv()
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
COGNITO_REDIRECT_URI = os.getenv("COGNITO_REDIRECT_URI")

# Build login URL
LOGIN_URL = (
    f"{COGNITO_DOMAIN}/login?"
    f"client_id={COGNITO_CLIENT_ID}"
    f"&response_type=code"
    f"&scope=email+openid"
    f"&redirect_uri={COGNITO_REDIRECT_URI}"
)

st.set_page_config(page_title="Stocks Analytics Portal", page_icon="📊")

# st.title("📊 Stocks Analytics Portal")
# query_params = st.experimental_get_query_params()
# # st.write("DEBUG QUERY PARAMS (legacy):", query_params)


# # Exchange auth code for tokens
# auth_code = query_params.get("code", [None])[0]
try:
    query_params = st.query_params
except AttributeError:
    # Fallback for older Streamlit versions
    query_params = st.experimental_get_query_params()

# Works for both old and new APIs
auth_code = None
if query_params:
    if isinstance(query_params.get("code"), list):
        auth_code = query_params.get("code", [None])[0]
    else:
        auth_code = query_params.get("code")
        
if auth_code and "tokens" not in st.session_state:
    basic_auth = base64.b64encode(f"{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}".encode()).decode()
    token_url = f"{COGNITO_DOMAIN}/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": COGNITO_CLIENT_ID,
        "code": auth_code,
        "redirect_uri": COGNITO_REDIRECT_URI,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {basic_auth}",
    }

    resp = requests.post(token_url, data=data, headers=headers)
    # st.write("Token response:", resp.status_code, resp.text)
    tokens = resp.json()
    st.session_state["tokens"] = tokens

    if "id_token" in tokens:
        decoded = jwt.get_unverified_claims(tokens["id_token"])
        st.session_state["user"] = decoded
        sync_user_to_db(decoded)
        st.rerun()

if "user" in st.session_state:
    user = st.session_state["user"]
    groups = user.get("cognito:groups", [])

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name, email, is_admin FROM users WHERE cognito_sub = :sub"),
            {"sub": user.get("sub")},
        ).fetchone()

    if result and result[0]:
        display_name = result[0]
    else:
        display_name = user.get("email", "Unknown user")
    st.empty()
    st.markdown("<div style='height: 100px'></div>", unsafe_allow_html=True)
    logout_url = (
        f"{COGNITO_DOMAIN}/logout?"
        f"client_id={COGNITO_CLIENT_ID}"
        f"&logout_uri={COGNITO_REDIRECT_URI}"
    )

    # Place logout button at top-right
    col1, col2 = st.columns([8, 1])
    with col2:
        st.markdown(f"""
        <div style='position: relative; text-align: right;'>
            <div class='dropdown'>
                <button class='dropbtn'>Profile ▾</button>
                <div class='dropdown-content'>
                    <a href='/update_details'>Update Details</a>
                    <a href='?action=logout'>Logout</a>
                </div>
            </div>
        </div>

        <style>
            /* Button */
            .dropbtn {{
                background-color: white;
                color: #333;
                padding: 8px 14px;
                font-size: 15px;
                border: 1px solid #ccc;
                border-radius: 8px;
                cursor: pointer;
                text-align: center;
                width: 150px; /* consistent width */
            }}
            .dropbtn:hover {{
                background-color: #f2f2f2;
            }}

            /* Dropdown container */
            .dropdown {{
                position: relative;
                display: inline-block;
            }}

            /* Dropdown menu */
            .dropdown-content {{
                display: none;
                position: absolute;
                left: 50%;
                transform: translateX(-50%); /* center under button */
                background-color: white;
                min-width: 150px;
                text-align: center; /* center text inside menu */
                box-shadow: 0px 8px 16px rgba(0,0,0,0.15);
                border-radius: 8px;
                z-index: 999;
            }}

            .dropdown-content a {{
                color: #333;
                padding: 10px 14px;
                text-decoration: none;
                display: block;
                font-size: 14px;
            }}
            .dropdown-content a:hover {{
                background-color: #f0f0f0;
            }}

            /* Show dropdown on hover */
            .dropdown:hover .dropdown-content {{
                display: block;
            }}
        </style>
        """, unsafe_allow_html=True)

    try:
        if "admin" in groups:
            module = importlib.import_module("admin_portal.app")
        else:
            module = importlib.import_module("user_portal.app")

        if hasattr(module, "page"):
            module.page()
        else:
            st.error("This portal is missing a page() function.")
    except ModuleNotFoundError as e:
        st.error(f"Portal not found: {e}")
    except Exception as e:
        st.error(f"Error loading portal: {e}")

# -------------------------
# Not logged in → show login button
# -------------------------
else:
    st.markdown("Please log in to continue.")
    st.markdown(
        f"""
        <style>
        .login-btn {{
            display: inline-block;
            padding: 0.6em 1.2em;
            background-color: white;
            color: #333; /* dark grey text */
            border: 1.5px solid #d3d3d3; /* light grey border */
            border-radius: 8px;
            text-decoration: none !important; /* remove underline */
            font-weight: 600;
            font-family: 'Segoe UI', sans-serif;
            transition: all 0.2s ease;
            cursor: pointer;
        }}
        .login-btn:hover {{
            background-color: #f0f0f0; /* light grey hover */
            border-color: #bfbfbf; /* slightly darker on hover */
            color: #000; /* darker text on hover */
            text-decoration: none !important; /* still no underline */
        }}
        </style>

        <a href="{LOGIN_URL}" target="_self" class="login-btn">Login / Sign Up to access the portal</a>
        """,
        unsafe_allow_html=True,
    )
