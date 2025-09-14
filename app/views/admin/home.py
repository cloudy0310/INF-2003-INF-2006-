import streamlit as st

def safe_rerun():
    if hasattr(st, "rerun"):
        return st.rerun()
    try:
        st.stop()
    except:
        pass

def admin_home(session, supabase):
    try:
        email = session.user.email
    except Exception:
        email = (session.get("user") or {}).get("email") if isinstance(session, dict) else None

    st.title("🔧 Admin Home")
    st.success(f"Welcome, {email} (admin)!")
    st.write("Put admin content here.")

    if st.button("Logout"):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state.user_session = None
        st.query_params = {"page": "login"}
        safe_rerun()
