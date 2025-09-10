# app/views/user/home.py
import streamlit as st
from app.supabase_helpers import rest_get

def render():
    st.title("Home — Contents")
    token = st.session_state.get("access_token")
    try:
        # Show only published content
        contents = rest_get("content?select=*&order=published_at.desc", access_token=token)
    except Exception as e:
        st.error(f"Failed to load content: {e}")
        contents = []

    if not contents:
        st.info("No content found.")
        return

    for c in contents:
        st.header(c.get("title"))
        if c.get("image_url"):
            st.image(c["image_url"], use_column_width=True)
        st.write(c.get("excerpt") or (c.get("body")[:400] + "..."))
        st.caption(f"Published: {c.get('published_at')} • Author: {c.get('author_id')}")
