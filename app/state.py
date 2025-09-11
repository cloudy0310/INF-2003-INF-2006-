# app/state.py
import streamlit as st

def init_state():
    defaults = {
        "user": None,
        "access_token": None,
        "profile": None,
        "refresh_token": None,  # optional if you use Supabase refresh
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
