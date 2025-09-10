# app/auth.py
import os
import streamlit as st
import requests
from typing import Optional, Dict
from app.supabase_helpers import get_client, get_auth_headers, rest_post, rest_get

def _create_supabase_client():
    return get_client()

def signup(email: str, password: str, username: str) -> Dict:
    """
    Sign up an auth user, then (recommended) create a row in `users` table.
    Note: if your DB disallows anon inserts into `users`, create the profile server-side.
    """
    supabase = _create_supabase_client()
    if supabase is None:
        return {"error": "supabase_not_configured"}
    # sign up using supabase-py
    resp = supabase.auth.sign_up({"email": email, "password": password})
    # supabase-py versions differ in response shape
    user = None
    access_token = None
    if isinstance(resp, dict):
        # newer versions may return {'data': {'user':...,'session':...}}
        data = resp.get("data") or resp
        user = data.get("user") or data.get("data", {}).get("user")
        session = data.get("session") or data.get("data", {}).get("session") or data.get("session")
        if session and isinstance(session, dict):
            access_token = session.get("access_token")
    # fallback: some versions return resp directly with 'user'
    if user is None and isinstance(resp, dict):
        user = resp.get("user")
    if user is None:
        # return raw response so caller can debug
        return {"error": "signup_failed", "resp": resp}

    user_id = user.get("id") or user.get("id")
    # create profile row via REST using anon key — this may be blocked by DB policies.
    try:
        # Use rest_post to call /rest/v1/users
        payload = {"user_id": user_id, "username": username, "email": email}
        r = rest_post("users", payload, access_token=None)
        # If insert blocked by RLS, r.status_code will reflect that.
        return {"user": user, "profile_status": r.status_code, "profile_text": r.text}
    except Exception as e:
        return {"user": user, "error_profile_insert": str(e)}

def login(email: str, password: str) -> Dict:
    supabase = _create_supabase_client()
    if supabase is None:
        return {"error": "supabase_not_configured"}
    # sign in
    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
    # extract token & user robustly:
    access_token = None
    user = None
    # check several possible response shapes:
    if isinstance(res, dict):
        data = res.get("data") or res
        # new SDK: data contains session & user
        session = data.get("session") or data.get("data", {}).get("session")
        if session and isinstance(session, dict):
            access_token = session.get("access_token")
            user = session.get("user")
        user = user or data.get("user") or data.get("data", {}).get("user")
    # fallback to get_user() (some versions)
    if user is None:
        try:
            u = supabase.auth.get_user()  # type: ignore
            user = u.get("data", {}).get("user")
        except Exception:
            pass

    if user:
        st.session_state["user"] = user
        if access_token:
            st.session_state["access_token"] = access_token
    return {"user": user, "access_token": access_token}

def logout():
    supabase = _create_supabase_client()
    if supabase:
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("user", None)
    st.session_state.pop("access_token", None)
    st.session_state.pop("profile", None)

def get_profile(user_id: str, access_token: Optional[str] = None) -> Optional[Dict]:
    """
    Query the custom `users` table for the profile row. Use user's JWT so RLS/auth.uid() works.
    """
    # call REST endpoint
    url = os.getenv("SUPABASE_URL") or (st.secrets.get("SUPABASE_URL") if hasattr(st, "secrets") else None)
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/users?user_id=eq.{user_id}"
    headers = get_auth_headers(access_token)
    r = requests.get(full, headers=headers)
    if r.status_code == 200:
        arr = r.json()
        return arr[0] if arr else None
    # return None on error to allow UI to show message
    return None
