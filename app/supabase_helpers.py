# app/supabase_helpers.py
import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
import requests
from typing import Optional, Tuple

# load .env if present
load_dotenv()

def _get_env_keys() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    # prefer Streamlit secrets if present
    supabase_url = None
    supabase_key = None
    service_role = None
    if hasattr(st, "secrets"):
        supabase_url = st.secrets.get("SUPABASE_URL") or supabase_url
        supabase_key = st.secrets.get("SUPABASE_ANON_KEY") or supabase_key
        service_role = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or service_role

    supabase_url = supabase_url or os.getenv("SUPABASE_URL")
    supabase_key = supabase_key or os.getenv("SUPABASE_ANON_KEY")
    service_role = service_role or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return supabase_url, supabase_key, service_role

def get_client():
    """
    Return a create_client(supabase_url, anon_key) or None when not configured.
    Use this client for high-level supabase-py calls. Don't use service_role here.
    """
    url, key, _ = _get_env_keys()
    if not url or not key:
        return None
    return create_client(url, key)

def get_auth_headers(access_token: Optional[str]):
    """
    Returns headers for REST calls. If access_token provided, use it as Bearer token.
    Otherwise fall back to anon key for read-only requests.
    """
    url, anon_key, _ = _get_env_keys()
    headers = {"apikey": anon_key} if anon_key else {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    headers["Content-Type"] = "application/json"
    return headers

def rest_get(table: str, params: str = "", access_token: Optional[str] = None):
    """
    GET from REST endpoint: table is e.g. "content?select=*" or "watchlists?user_id=eq.<id>"
    """
    url, _, _ = _get_env_keys()
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/{table}{params}"
    headers = get_auth_headers(access_token)
    r = requests.get(full, headers=headers)
    r.raise_for_status()
    return r.json()

def rest_post(table: str, payload: dict, access_token: Optional[str] = None):
    url, _, _ = _get_env_keys()
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/{table}"
    headers = get_auth_headers(access_token)
    r = requests.post(full, headers=headers, json=payload)
    return r

def rest_delete(table: str, filter_query: str, access_token: Optional[str] = None):
    """
    filter_query example: "id=eq.<uuid>"
    """
    url, _, _ = _get_env_keys()
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/{table}?{filter_query}"
    headers = get_auth_headers(access_token)
    r = requests.delete(full, headers=headers)
    return r
