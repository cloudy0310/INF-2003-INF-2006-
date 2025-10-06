# login/app.py
import streamlit as st
from datetime import datetime, timezone
from pathlib import Path
import sys

# --- allow imports from sibling folders (admin_portal, user_portal)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from login.supa import get_client

st.set_page_config(page_title="Login / Signup",  layout="centered")
sb = get_client()

# ---- session bootstrap
if "auth" not in st.session_state:
    st.session_state.auth = {
        "logged_in": False,
        "user_id": None,
        "email": None,
        "username": None,
        "is_admin": False,
    }

# ---- helpers
def fetch_profile(uid: str):
    """Fetch profile row from your public.users table by user_id."""
    res = sb.table("users").select("user_id,username,email,is_admin").eq("user_id", uid).maybe_single().execute()
    return res.data

def ensure_profile(uid: str, email: str, username: str | None = None):
    """Create profile row if missing."""
    prof = fetch_profile(uid)
    if prof is None:
        sb.table("users").insert({
            "user_id": uid,
            "email": email,
            "username": username or email.split("@")[0],
            "is_admin": False
        }).execute()
        prof = fetch_profile(uid)
    return prof

def update_last_login(uid: str):
    sb.table("users").update({
        "last_login_at": datetime.now(timezone.utc).isoformat()
    }).eq("user_id", uid).execute()

def _render_admin():
    from admin_portal.app import render as admin_render
    admin_render()

def _render_user():
    from user_portal.app import render as user_render
    user_render()

def logout():
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    st.session_state.auth = {
        "logged_in": False, "user_id": None, "email": None, "username": None, "is_admin": False
    }
    # st.rerun()

if st.session_state.auth["logged_in"]:
    # --- Sticky logout bar CSS (below Streamlit header) ---
    st.markdown(
        """
        <style>
        /* Target Streamlit's built-in app header */
        .stAppHeader {
            z-index: 999 !important;
        }

        /* Our custom logout bar */
        .logout-bar {
            position: fixed;
            top: 3.5rem;  
            left: 0;
            right: 0;
            padding: 0.6rem 1rem;
            background-color: #ffffff;
            z-index: 1000;  
        }

        .block-container {
            padding-top: 7rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # --- Sticky logout bar UI ---
    st.markdown('<div class="logout-bar">', unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1])
    c1.caption(
        f"Signed in as **{st.session_state.auth['email']}** "
        f"({'admin' if st.session_state.auth['is_admin'] else 'user'})"
    )
    c2.button("Logout", on_click=logout, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Role-based rendering ---
    if st.session_state.auth["is_admin"]:
        _render_admin()
    else:
        _render_user()

    st.stop()

# ---- UI
tabs = st.tabs(["Login", "Sign up"])

# -------- LOGIN TAB --------
with tabs[0]:
    st.subheader("Login")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_pw")
    if st.button("Sign in", type="primary", use_container_width=True):
        try:
            res = sb.auth.sign_in_with_password({"email": email, "password": password})
            user = res.user
            if not user:
                st.error("Invalid email or password.")
            else:
                prof = ensure_profile(user.id, email)
                update_last_login(user.id)
                st.session_state.auth = {
                    "logged_in": True,
                    "user_id": user.id,
                    "email": prof.get("email", email),
                    "username": prof.get("username"),
                    "is_admin": bool(prof.get("is_admin", False)),
                }
                st.success("Logged in. Redirecting…")
                st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")

# -------- SIGNUP TAB --------
with tabs[1]:
    st.subheader("Create an account")
    su_email = st.text_input("Email", key="su_email")
    su_username = st.text_input("Username (display name)", key="su_username")
    su_password = st.text_input("Password (min 6 chars)", type="password", key="su_pw")

    if st.button("Sign up", use_container_width=True):
        try:
            res = sb.auth.sign_up({"email": su_email, "password": su_password,
                                   "options": {"data": {"username": su_username}}})
            user = res.user
            if not user:
                st.error("Sign up failed.")
            else:
                sb.table("users").upsert({
                    "user_id": user.id,
                    "email": su_email,
                    "username": su_username or su_email.split("@")[0],
                    "is_admin": False,   # keep false; promote manually in DB when needed
                }, on_conflict="user_id").execute()

                st.success("Account created! Check email if confirmation is required, then log in.")
        except Exception as e:
            st.error(f"Sign up failed: {e}")
