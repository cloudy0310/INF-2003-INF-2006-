# app/router.py
import streamlit as st

def route():
    # local imports to avoid circular import
    from app.views import landing
    from app.views.user import home, stock_analysis, news, watchlist
    from app.views.admin import dashboard
    from app.auth import get_profile

    user = st.session_state.get("user")
    token = st.session_state.get("access_token")
    profile = st.session_state.get("profile")

    if not user:
        landing.render()
        return

    if not profile:
        try:
            profile = get_profile(user.get("id") or user.get("user_metadata", {}).get("id") or user.get("sub"), access_token=token)
        except Exception as e:
            st.error(f"Failed to load profile: {e}")
            profile = None
        st.session_state["profile"] = profile

    tabs = ["Home", "Stock Analysis", "News", "Watchlist"]
    if profile and profile.get("is_admin"):
        tabs.append("Admin Dashboard")

    tab_objs = st.tabs(tabs)
    for name, tab_ctx in zip(tabs, tab_objs):
        with tab_ctx:
            if name == "Home":
                home.render()
            elif name == "Stock Analysis":
                stock_analysis.render()
            elif name == "News":
                news.render()
            elif name == "Watchlist":
                watchlist.render()
            elif name == "Admin Dashboard":
                dashboard.render()
