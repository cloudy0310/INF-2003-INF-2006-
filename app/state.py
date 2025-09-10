# app/state.py
import streamlit as st

def init_state():
    if "user" not in st.session_state:
        st.session_state["user"] = None
    if "access_token" not in st.session_state:
        st.session_state["access_token"] = None
    if "profile" not in st.session_state:
        st.session_state["profile"] = None
