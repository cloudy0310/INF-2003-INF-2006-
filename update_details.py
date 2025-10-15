import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Database setup ---
DB_HOST = os.getenv("RDS_HOST")
DB_PORT = os.getenv("RDS_PORT", "5432")
DB_NAME = os.getenv("RDS_DB")
DB_USER = os.getenv("RDS_USER")
DB_PASS = os.getenv("RDS_PASSWORD")

engine = create_engine(
    f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    echo=False
)

# --- Page setup ---
st.set_page_config(page_title="Update Details", page_icon="📝", layout="centered")
st.title("📝 Update Your Details")

if "user" not in st.session_state:
    st.warning("⚠️ You must be logged in to update your details.")
    st.stop()

user = st.session_state["user"]
cognito_sub = user.get("sub")

# Fetch existing user details
with engine.connect() as conn:
    result = conn.execute(
        text("SELECT name, email FROM users WHERE cognito_sub = :sub"),
        {"sub": cognito_sub},
    ).fetchone()

name = result[0] if result and result[0] else ""
email = result[1] if result and result[1] else user.get("email", "")

# --- Form ---
with st.form("update_form"):
    new_name = st.text_input("Full Name", value=name)
    new_email = st.text_input("Email", value=email)
    submitted = st.form_submit_button("💾 Save Changes")

    if submitted:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE users
                        SET name = :name, email = :email, updated_at = NOW()
                        WHERE cognito_sub = :sub
                    """),
                    {"name": new_name, "email": new_email, "sub": cognito_sub},
                )
            st.success("✅ Your details have been updated successfully!")
        except SQLAlchemyError as e:
            st.error(f"Database error: {e}")

# --- Back button ---
st.markdown(
    """
    <br>
    <a href="/" class="back-btn">← Back to Dashboard</a>

    <style>
    .back-btn {
        display: inline-block;
        padding: 0.5em 1em;
        background-color: #f2f2f2;
        color: #333;
        border: 1px solid #ccc;
        border-radius: 6px;
        text-decoration: none;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    .back-btn:hover {
        background-color: #e6e6e6;
        border-color: #aaa;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
