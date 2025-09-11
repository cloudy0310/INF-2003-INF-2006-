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
            # debug: show raw response for troubleshooting
            st.write("login response (raw):", res.get("raw"))
            if res.get("error"):
                st.error(f"Login error: {res.get('error')}")
            else:
                user = res.get("user")
                token = res.get("access_token") or st.session_state.get("access_token")
                st.success("Logged in")
                # store again (defensive)
                st.session_state["user"] = user
                if token:
                    st.session_state["access_token"] = token

                # try to load profile using user's id and token (profile table uses user_id)
                try:
                    # user may be dict-like or object; probe common keys
                    user_id = None
                    if isinstance(user, dict):
                        user_id = user.get("id") or user.get("sub") or user.get("user_id")
                    else:
                        user_id = getattr(user, "id", None) or getattr(user, "sub", None)
                    if user_id:
                        profile = get_profile(user_id, access_token=token)
                        st.session_state["profile"] = profile
                        st.write("Loaded profile:", profile)
                    else:
                        st.info("Logged in but couldn't find user id in returned user object.")
                except Exception as e:
                    st.warning(f"Logged in but failed to load profile: {e}")

                st.rerun()

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
                # debug
                st.write("signup response (raw):", res.get("raw"))
                if res.get("error"):
                    st.error(f"Signup failed: {res.get('error')}")
                else:
                    user = res.get("user")
                    token = res.get("access_token") or st.session_state.get("access_token")
                    st.success("Account created.")
                    # store
                    st.session_state["user"] = user
                    if token:
                        st.session_state["access_token"] = token

                    # attempt to load profile
                    try:
                        user_id = None
                        if isinstance(user, dict):
                            user_id = user.get("id") or user.get("sub") or user.get("user_id")
                        else:
                            user_id = getattr(user, "id", None) or getattr(user, "sub", None)
                        if user_id:
                            profile = get_profile(user_id, access_token=token)
                            st.session_state["profile"] = profile
                            st.write("Loaded profile:", profile)
                        else:
                            st.info("Signed up but couldn't find user id in returned user object.")
                    except Exception as e:
                        st.warning(f"Signed up, but failed to load profile: {e}")

                    st.rerun()

    st.markdown("---")
    st.caption("If you see configuration errors (missing Supabase keys), check `.streamlit/secrets.toml` or your `.env`.")
    # Helpful debug: show whether secrets are loaded
    try:
        supabase_url = st.secrets.get("SUPABASE", {}).get("SUPABASE_URL")
        st.caption(f"Supabase URL loaded: {bool(supabase_url)}")
    except Exception:
        pass
