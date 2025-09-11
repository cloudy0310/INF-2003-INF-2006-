# app/supabase_helpers.py
import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client
import requests
from typing import Optional, Tuple

# Load .env if present
load_dotenv()

def _get_env_keys() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY"""
    supabase_url = None
    supabase_key = None
    service_role = None

    # Streamlit secrets take precedence
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
    Return supabase client (supabase-py) using anon key.
    Service role should not be used here.
    """
    url, key, _ = _get_env_keys()
    if not url or not key:
        return None
    return create_client(url, key)

def get_auth_headers(access_token: Optional[str] = None):
    """
    Returns headers for REST calls:
    - Include 'apikey' always (Supabase requires it)
    - Include 'Authorization: Bearer <token>' if access_token provided
    """
    _, anon_key, _ = _get_env_keys()
    if not anon_key:
        raise RuntimeError("SUPABASE_ANON_KEY not configured")

    headers = {
        "apikey": anon_key,
        "Content-Type": "application/json"
    }

    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    return headers


def rest_get(table: str, params: str = "", access_token: Optional[str] = None):
    """
    GET from REST endpoint: table is e.g. "content" or "watchlists"
    Params is optional query string: "?select=*&order=published_at.desc"
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
    """
    POST to REST endpoint
    Returns response JSON if successful.
    """
    url, _, _ = _get_env_keys()
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/{table}"
    headers = get_auth_headers(access_token)
    headers["Prefer"] = "return=representation"
    resp = requests.post(full, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()

def rest_patch(table: str, filter_query: str, payload: dict, access_token: Optional[str] = None):
    """
    PATCH (update) rows matching filter_query
    filter_query example: "id=eq.<uuid>"
    """
    url, _, _ = _get_env_keys()
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/{table}?{filter_query}"
    headers = get_auth_headers(access_token)
    headers["Prefer"] = "return=representation"
    resp = requests.patch(full, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()

def rest_delete(table: str, filter_query: str, access_token: Optional[str] = None):
    """
    DELETE rows matching filter_query
    filter_query example: "id=eq.<uuid>"
    """
    url, _, _ = _get_env_keys()
    if not url:
        raise RuntimeError("SUPABASE_URL not configured")
    full = f"{url}/rest/v1/{table}?{filter_query}"
    headers = get_auth_headers(access_token)
    headers["Prefer"] = "return=representation"
    resp = requests.delete(full, headers=headers)
    resp.raise_for_status()
    return resp.json()
