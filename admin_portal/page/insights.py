# user_page/insights.py

import pandas as pd
import streamlit as st
import plotly.express as px
from sqlalchemy.engine import Engine

def page(rds: Engine = None):
    st.set_page_config(page_title="Market Insights", layout="wide")
    st.title("📊 Market Insights")
    st.caption("Top performing sectors from recent data")

    if rds is None:
        st.error("RDS engine is required.")
        st.stop()

    # Optional sector filter (if applicable in your data)
    st.subheader("🔍 Sector Performance Overview")
    col1, col2 = st.columns([1, 2])
    with col1:
        limit = st.slider("Number of sectors to show", 5, 50, 20)

    try:
        query = f"""
            SELECT sector, performance 
            FROM sector_performance 
            WHERE performance IS NOT NULL
            ORDER BY performance DESC
            LIMIT {limit}
        """
        df = pd.read_sql(query, rds)
    except Exception as e:
        st.error(f"❌ Failed to load sector performance data: {e}")
        return

    if df.empty:
        st.info("No sector performance data found.")
        return

    fig = px.bar(
        df,
        x="sector",
        y="performance",
        title=f"Top {limit} Sector Performances",
        color="performance",
        color_continuous_scale="Blues",
        labels={"sector": "Sector", "performance": "Performance"},
    )

    fig.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_tickangle=-45
    )

    st.plotly_chart(fig, use_container_width=True)

    # Optionally show the raw data table
    with st.expander("🧾 Show raw data"):
        st.dataframe(df, use_container_width=True)
