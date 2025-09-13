import streamlit as st
from app.auth import login, signup, get_profile

def render():
    st.title("Welcome — sign in or create an account")

    # Create login/signup tabs
    login_tab, signup_tab = st.tabs(["Login", "Sign up"])

    # ---------- LOGIN TAB ----------
    with login_tab:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        pw = st.text_input("Password", type="password", key="login_pw")

        if st.button("Login", key="login_btn"):
            res = login(email, pw)
            if res.get("error"):
                st.error(f"Login error: {res.get('error')}")
            else:
                # store user and token in session state
                user = res.get("user")
                token = res.get("access_token") or st.session_state.get("access_token")
                st.session_state["user"] = user
                if token:
                    st.session_state["access_token"] = token

                # try to load profile
                try:
                    user_id = user.get("id") or user.get("sub") or user.get("user_id")
                    if user_id:
                        profile = get_profile(user_id, access_token=token)
                        st.session_state["profile"] = profile
                except Exception as e:
                    st.warning(f"Failed to load profile: {e}")

                # redirect to default tab
                st.session_state["active_tab"] = "Stock Analysis"
                st.experimental_rerun()  # rerun to go to router

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
                if res.get("error"):
                    st.error(f"Signup failed: {res.get('error')}")
                else:
                    # store user and token
                    user = res.get("user")
                    token = res.get("access_token") or st.session_state.get("access_token")
                    st.session_state["user"] = user
                    if token:
                        st.session_state["access_token"] = token

                    # load profile
                    try:
                        user_id = user.get("id") or user.get("sub") or user.get("user_id")
                        if user_id:
                            profile = get_profile(user_id, access_token=token)
                            st.session_state["profile"] = profile
                    except Exception as e:
                        st.warning(f"Failed to load profile: {e}")

                    # redirect to default tab
                    st.session_state["active_tab"] = "Stock Analysis"
                    st.experimental_rerun()  # rerun to go to router

    st.markdown("---")
    st.caption("Check your Supabase keys if there are configuration errors.")
