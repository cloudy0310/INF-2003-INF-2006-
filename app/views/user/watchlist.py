# app/views/user/watchlist.py
import streamlit as st
from app.supabase_helpers import rest_get

def render():
    st.title("Watchlists")
    profile = st.session_state.get("profile")
    token = st.session_state.get("access_token")
    if not profile:
        st.info("Profile not loaded.")
        return
    user_id = profile.get("user_id") or profile.get("user_id")
    try:
        wlists = rest_get(f"watchlists?user_id=eq.{user_id}&select=*", access_token=token)
    except Exception as e:
        st.error(f"Failed to load watchlists: {e}")
        return

    if not wlists:
        st.info("No watchlists yet.")
        return

    for w in wlists:
        st.subheader(w.get("name"))
        st.write(w.get("description") or "")
