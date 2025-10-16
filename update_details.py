import streamlit as st
import os
import boto3
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

DB_HOST = os.getenv("RDS_HOST")
DB_PORT = os.getenv("RDS_PORT", "5432")
DB_NAME = os.getenv("RDS_DB")
DB_USER = os.getenv("RDS_USER")
DB_PASS = os.getenv("RDS_PASSWORD")
COGNITO_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")

engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require",
    pool_pre_ping=True,
    future=True,
    echo=False,
)

def page():
    st.set_page_config(page_title="Update Details", layout="centered")

    if "user" not in st.session_state:
        st.warning("Please log in first.")
        st.stop()

    user = st.session_state["user"]
    cognito_sub = user.get("sub")
    username = user.get("cognito:username")

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name, email FROM users WHERE cognito_sub = :sub"),
            {"sub": cognito_sub},
        ).fetchone()

    current_name = result[0] if result else user.get("name", "")
    current_email = result[1] if result else user.get("email", "")

    st.markdown("## Update Your Details")
    with st.form("update_form"):
        new_name = st.text_input("Full Name", value=current_name)
        new_email = st.text_input("Email Address", value=current_email)

        col1, col2 = st.columns([3, 1])
        with col1:
            cancel = st.form_submit_button("Cancel")
        with col2:
            submitted = st.form_submit_button("Save Changes", use_container_width=True)


    # Handle cancel button (redirect to dashboard)
    if cancel:
        st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
        st.stop()

    if submitted:
        if not new_name or not new_email:
            st.error("Both name and email are required.")
            st.stop()

        try:
            client = boto3.client("cognito-idp", region_name=COGNITO_REGION)

            # Update Cognito attributes
            client.admin_update_user_attributes(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=username,
                UserAttributes=[
                    {"Name": "name", "Value": new_name},
                    {"Name": "email", "Value": new_email},
                ]
            )

            # Update in RDS
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        UPDATE users
                        SET name = :name, email = :email
                        WHERE cognito_sub = :sub
                    """),
                    {"name": new_name, "email": new_email, "sub": cognito_sub},
                )

            # Refresh session attributes
            response = client.admin_get_user(
                UserPoolId=COGNITO_USER_POOL_ID,
                Username=username,
            )
            updated_attrs = {a["Name"]: a["Value"] for a in response["UserAttributes"]}
            st.session_state["user"].update(updated_attrs)

            st.success("Profile updated successfully!")
            st.markdown("<meta http-equiv='refresh' content='2;url=/' />", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Error updating details: {e}")
