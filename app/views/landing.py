# app/views/landing.py
import streamlit as st
from app.auth import login, signup, get_profile

def render():
    st.title("Welcome — sign in or create an account")

    login_tab, signup_tab = st.tabs(["Login", "Sign up"])

    # ---------- LOGIN TAB ----------
    with login_tab:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        pw = st.text_input("Password", type="password", key="login_pw")
        if st.button("Login", key="login_btn"):
            res = login(email, pw)
            user = res.get("user")
            token = res.get("access_token") or st.session_state.get("access_token")
            if user:
                # store user and token (login() may already do this)
                st.session_state["user"] = user
                if token:
                    st.session_state["access_token"] = token

                # try to load profile using user's id and token (profile table uses user_id)
                try:
                    # some SDKs use id at user["id"]; fall back to "sub" or "user_id"
                    user_id = user.get("id") or user.get("sub") or user.get("user_id")
                    profile = get_profile(user_id, access_token=token)
                    st.session_state["profile"] = profile
                except Exception as e:
                    st.warning(f"Logged in but failed to load profile: {e}")

                st.success("Logged in")
                st.experimental_rerun()
            else:
                st.error(f"Login failed: {res}")

    # ---------- SIGNUP TAB ----------
    with signup_tab:
        st.subheader("Create an account")
        username = st.text_input("Username", key="signup_username")
        email_s = st.text_input("Email", key="signup_email")
        pw_s = st.text_input("Password", type="password", key="signup_pw")
        if st.button("Sign up", key="signup_btn"):
            if not username:
                st.error("Please enter a username.")
            else:
                res = signup(email_s, pw_s, username)
                user = res.get("user")
                # If signup created a user, attempt to auto-login (if token available)
                if user:
                    st.success("Account created. Attempting to log you in...")
                    # try to sign in immediately
                    login_res = login(email_s, pw_s)
                    user2 = login_res.get("user")
                    token2 = login_res.get("access_token") or st.session_state.get("access_token")
                    if user2:
                        st.session_state["user"] = user2
                        if token2:
                            st.session_state["access_token"] = token2
                        # load profile
                        try:
                            user_id = user2.get("id") or user2.get("sub") or user2.get("user_id")
                            profile = get_profile(user_id, access_token=token2)
                            st.session_state["profile"] = profile
                        except Exception as e:
                            st.warning(f"Signed up, but failed to load profile: {e}")
                        st.success("Signed up and logged in.")
                        st.experimental_rerun()
                    else:
                        st.info("Signed up — please login using the Login tab.")
                else:
                    st.error(f"Signup failed: {res}")

    # Optional small note and troubleshooting help
    st.markdown("---")
    st.caption("If you see configuration errors (missing Supabase keys), check `.streamlit/secrets.toml` or your `.env`.")
