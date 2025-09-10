# app.py
import streamlit as st
from app.state import init_state
from app.router import route

st.set_page_config(page_title="My Stock App", layout="wide")
init_state()
route()
