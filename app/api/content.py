# app/api/content_api.py
from typing import List, Dict, Optional
from app.supabase_helpers import rest_get, rest_post, rest_delete
import streamlit as st

def get_latest_content(access_token: Optional[str] = None) -> List[Dict]:
    """
    Fetch latest published content ordered by published_at descending.
    """
    try:
        # Positional argument for params
        return rest_get("content", "?select=*&order=published_at.desc", access_token)
    except Exception as e:
        st.error(f"Failed to load content: {e}")
        return []


def get_content_by_id(content_id: str, access_token: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch a single content item by its ID.
    """
    try:
        results = rest_get(
            table="content",
            params=f"?select=*&id=eq.{content_id}",
            access_token=access_token
        )
        return results[0] if results else None
    except Exception as e:
        st.error(f"Failed to load content: {e}")
        return None

def create_content(payload: Dict, access_token: Optional[str] = None) -> Dict:
    """
    Create a new content item.
    - payload: dict with fields like title, body, author_id, etc.
    """
    try:
        r = rest_post("content", payload, access_token=access_token)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Failed to create content: {e}")
        return {}

def delete_content(content_id: str, access_token: Optional[str] = None) -> bool:
    """
    Delete content by ID.
    Returns True if deletion succeeded.
    """
    try:
        r = rest_delete("content", f"id=eq.{content_id}", access_token=access_token)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Failed to delete content: {e}")
        return False
