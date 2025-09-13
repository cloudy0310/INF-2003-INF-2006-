import streamlit as st

def route():
    from app.views import landing
    from app.views.user import home, stock_analysis, news, watchlist
    from app.views.admin import dashboard

    user = st.session_state.get("user")
    profile = st.session_state.get("profile")

    # --- Not logged in: show landing page ---
    if not user:
        landing.render()
        return

    # --- NAV BAR ---
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"👋 Logged in as **{user.get('user_metadata', {}).get('email') or user.get('email')}**")
    with col2:
        if st.button("🚪 Log out"):
            for key in ["user", "access_token", "profile", "active_tab"]:
                st.session_state.pop(key, None)
            st.rerun()

    # --- TABS ---
    tabs = ["Home", "Stock Analysis", "News", "Watchlist"]
    if profile and profile.get("is_admin"):
        tabs.append("Admin Dashboard")

    # remember which tab is active
    if "active_tab" not in st.session_state or st.session_state["active_tab"] not in tabs:
        st.session_state["active_tab"] = "Home"

    tab_objs = st.tabs(tabs)

    for name, tab_ctx in zip(tabs, tab_objs):
        with tab_ctx:
            if name == st.session_state["active_tab"]:
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
