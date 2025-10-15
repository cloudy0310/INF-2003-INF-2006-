import streamlit as st
import os
import base64
import requests
from jose import jwt
from dotenv import load_dotenv
import importlib
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote  # already added earlier
from streamlit_cookies_manager import CookieManager
load_dotenv()
# Load DB credentials
DB_HOST = os.getenv("RDS_HOST")
DB_PORT = os.getenv("RDS_PORT", "5432")
DB_NAME = os.getenv("RDS_DB")
DB_USER = os.getenv("RDS_USER")
DB_PASS = os.getenv("RDS_PASSWORD")

# Create engine
engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require",
    pool_pre_ping=True,
    future=True,
    echo=False,
)
def _derive_name(claims: dict, email: str | None):
    # 1) Full name typed at signup (preferred)
    n = (claims.get("name") or "").strip()
    if n:
        return n
    return None


def _fetch_userinfo(domain: str, access_token: str) -> dict | None:
    try:
        r = requests.get(
            f"{domain.rstrip('/')}/oauth2/userInfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None
def sync_user_to_db(user_claims):
    """Insert or update a user record in PostgreSQL from Cognito claims."""
    try:
        with engine.begin() as conn:
            cognito_sub = user_claims.get("sub")
            email = user_claims.get("email")
            username = user_claims.get("cognito:username", email.split("@")[0] if email else "unknown")
            name = _derive_name(user_claims, email)
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

COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
COGNITO_REDIRECT_URI = os.getenv("COGNITO_REDIRECT_URI")

# Build login URL
AUTHORIZE_URL = (
    f"{COGNITO_DOMAIN.rstrip('/')}/oauth2/authorize"
    f"?client_id={COGNITO_CLIENT_ID}"
    f"&response_type=code"
    f"&scope=email+openid+profile"
    f"&redirect_uri={COGNITO_REDIRECT_URI}"
)

st.set_page_config(page_title="Stocks Analytics Portal", page_icon="📊")
cookies = CookieManager()
if not cookies.ready():
    st.stop()  # first run needs a rerender for cookies to be ready
# --- handle logout action early ---
try:
    qp = st.query_params
except AttributeError:
    qp = st.experimental_get_query_params()

action = None
if qp:
    action = qp.get("action", [None])[0] if isinstance(qp.get("action"), list) else qp.get("action")

if action == "logout":
    # Clear app session
    st.session_state.pop("tokens", None)
    st.session_state.pop("user", None)
    st.session_state.pop("user_synced", None)

    # Clear cookies
    cookies['rt'] = ''
    cookies['idt'] = ''
    cookies['idt_exp'] = ''
    cookies.save()

    # Clear local query params so we don't keep ?action=logout around
    try:
        st.query_params.clear()
    except Exception:
        st.experimental_set_query_params()

    # Send to Cognito logout; return to EXACT URL configured in "Sign out URL(s)"
    logout_return = COGNITO_REDIRECT_URI  # e.g. http://localhost:8501
    logout_url = (
        f"{COGNITO_DOMAIN.rstrip('/')}/logout"
        f"?client_id={COGNITO_CLIENT_ID}"
        f"&logout_uri={quote(logout_return, safe='')}"
    )
    st.markdown(f'<meta http-equiv="refresh" content="0; url={logout_url}" />', unsafe_allow_html=True)
    st.stop()


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

# ---- Works for both old and new APIs ----
try:
    query_params = st.query_params
except AttributeError:
    query_params = st.experimental_get_query_params()

# Normalize ?code param
auth_code = None
if query_params:
    if isinstance(query_params.get("code"), list):
        auth_code = query_params.get("code", [None])[0]
    else:
        auth_code = query_params.get("code")

# ---- Exchange ?code=... for tokens (only once) ----
tokens = st.session_state.get("tokens")
decoded = None
# 🍪 INSTANT RESTORE from cookie (skip Hosted-UI bounce)
import time
if not st.session_state.get("user"):
    idt_cookie = cookies.get('idt')
    idt_exp = cookies.get('idt_exp')
    if idt_cookie and idt_exp:
        try:
            if int(idt_exp) > int(time.time()):
                # still valid — restore user immediately (no network)
                st.session_state["user"] = jwt.get_unverified_claims(idt_cookie)
                # also seed tokens dict so downstream logic works
                t = st.session_state.get("tokens") or {}
                t["id_token"] = idt_cookie
                st.session_state["tokens"] = t
        except Exception:
            pass

# Try refresh flow if we have a refresh_token but no decoded user yet
if not st.session_state.get("user"):
    # ✅ get RT from session OR cookie BEFORE deciding to refresh
    t = st.session_state.get("tokens") or {}
    rt = t.get("refresh_token") or cookies.get('rt')  # <— moved up

    if rt:
        token_url = f"{COGNITO_DOMAIN.rstrip('/')}/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": COGNITO_CLIENT_ID,
            "refresh_token": rt,
        }
        auth = (COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET) if COGNITO_CLIENT_SECRET else None
        r = requests.post(token_url, data=data,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          auth=auth)

        idt2 = None  # avoid NameError on failure

        if r.status_code == 200:
            newt = r.json()
            if "refresh_token" not in newt and rt:
                newt["refresh_token"] = rt
            st.session_state["tokens"] = newt

            # 🍪 update cookies (rotate id token; keep RT)
            cookies['rt'] = rt
            idt2 = newt.get("id_token")
            if idt2:
                cookies['idt'] = idt2
                try:
                    c2 = jwt.get_unverified_claims(idt2)
                    cookies['idt_exp'] = str(c2.get('exp', ''))
                except Exception:
                    cookies['idt_exp'] = ''
            cookies.save()

            if idt2:
                st.session_state["user"] = jwt.get_unverified_claims(idt2)


if auth_code and "tokens" not in st.session_state:
    token_url = f"{COGNITO_DOMAIN.rstrip('/')}/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": COGNITO_REDIRECT_URI,
        "client_id": COGNITO_CLIENT_ID,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # Confidential client: include Basic auth
    auth = None
    if COGNITO_CLIENT_SECRET:
        auth = (COGNITO_CLIENT_ID, COGNITO_CLIENT_SECRET)

    resp = requests.post(token_url, data=data, headers=headers, auth=auth)

    if resp.status_code == 200:
        tokens = resp.json()
        st.session_state["tokens"] = tokens

        # 🍪 SAVE refresh token (and id token for instant claims)
        rt = tokens.get("refresh_token")
        if rt:
            cookies['rt'] = rt
        idt = tokens.get("id_token")
        if idt:
            cookies['idt'] = idt
        # store exp so we can ignore stale idt
            try:
                claims = jwt.get_unverified_claims(idt)
                cookies['idt_exp'] = str(claims.get('exp', ''))
            except Exception:
                cookies['idt_exp'] = ''
        cookies.save()

    # Clean URL and rerun
        try:
            st.query_params.clear()
        except Exception:
            st.experimental_set_query_params()
        st.rerun()
    else:
        st.error("Login failed. Please try again.")
        # (Optional) st.caption(resp.text)

# ---- Decode claims (only if we have an id_token) ----
tokens = st.session_state.get("tokens")
if tokens and isinstance(tokens, dict):
    idt = tokens.get("id_token")
    if idt:
        decoded = jwt.get_unverified_claims(idt)
        st.session_state["user"] = decoded
        # Upsert user just once per session
        if not st.session_state.get("user_synced"):
            sync_user_to_db(decoded)
            st.session_state["user_synced"] = True
else:
    # If you want silence on first load, remove this error entirely
    if auth_code and "tokens" in st.session_state:
        st.error("Could not complete login. Please try again.")

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
            color: #333;
            border: 1.5px solid #d3d3d3;
            border-radius: 8px;
            text-decoration: none !important;
            font-weight: 600;
            font-family: 'Segoe UI', sans-serif;
            transition: all 0.2s ease;
            cursor: pointer;
        }}
        .login-btn:hover {{
            background-color: #f0f0f0;
            border-color: #bfbfbf;
            color: #000;
            text-decoration: none !important;
        }}
        </style>
        <a href="{AUTHORIZE_URL}" target="_self" class="login-btn">
            Login / Sign Up to access the portal
        </a>
        """,
        unsafe_allow_html=True,
    )

