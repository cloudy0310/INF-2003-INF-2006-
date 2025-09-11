import streamlit as st
from app.api import content

def render():
    st.title("Home — Contents")
    token = st.session_state.get("access_token")

    contents = content.get_latest_content(access_token=token)
    if not contents:
        st.info("No content found.")
        return

    for c in contents:
        st.header(c.get("title"))
        if c.get("image_url"):
            st.image(c["image_url"], use_column_width=True)
        st.write(c.get("excerpt") or (c.get("body")[:400] + "..."))
        st.caption(f"Published: {c.get('published_at')} • Author: {c.get('author_id')}")
