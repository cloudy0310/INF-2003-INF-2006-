# app/views/admin/dashboard.py
import streamlit as st
from app.supabase_helpers import rest_get, get_auth_headers
import os
import requests

def render():
    st.title("Admin Dashboard — Content CRUD")
    token = st.session_state.get("access_token")
    profile = st.session_state.get("profile")

    if not profile or not profile.get("is_admin"):
        st.error("Admin access required.")
        return

    headers = get_auth_headers(token)

    st.subheader("Create content")
    title = st.text_input("Title", key="admin_title")
    body = st.text_area("Body", key="admin_body")
    if st.button("Create content"):
        url = f"{os.getenv('SUPABASE_URL') or (st.secrets.get('SUPABASE_URL') if hasattr(st, 'secrets') else None)}/rest/v1/content"
        payload = {
            "title": title,
            "body": body,
            "author_id": profile.get("user_id")
        }
        r = requests.post(url, headers=headers, json=payload)
        if r.status_code in (200, 201, 204):
            st.success("Content created")
        else:
            st.error(f"Create failed: {r.status_code} {r.text}")

    st.subheader("Existing content")
    try:
        contents = rest_get("content?select=*&order=created_at.desc", access_token=token)
    except Exception as e:
        st.error(f"Failed to load content: {e}")
        contents = []

    for c in contents:
        st.markdown(f"**{c.get('title')}**")
        cols = st.columns([6,1,1])
        cols[0].write(c.get("excerpt") or (c.get("body")[:200] + "..."))
        if cols[1].button(f"Edit {c['id']}", key=f"edit-{c['id']}"):
            st.info("Edit not implemented in this template.")
        if cols[2].button(f"Delete {c['id']}", key=f"del-{c['id']}"):
            del_url = f"{os.getenv('SUPABASE_URL') or (st.secrets.get('SUPABASE_URL') if hasattr(st, 'secrets') else None)}/rest/v1/content?id=eq.{c['id']}"
            r = requests.delete(del_url, headers=headers)
            if r.status_code in (200,204):
                st.success("Deleted")
                st.rerun()
            else:
                st.error(f"Delete failed: {r.status_code} {r.text}")
