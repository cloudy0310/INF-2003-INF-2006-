import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timedelta, timezone

# ----------------- Cached Data Fetch -----------------
@st.cache_data(ttl=900)
def fetch_sector_performance(days: int, limit: int, page: int, _rds):
    """
    Fetches the top performing sectors from your SQL database.
    Streamlit will ignore _rds when caching.
    """
    try:
        query = f"""
        SELECT sector, performance FROM sector_performance
        WHERE performance IS NOT NULL
        ORDER BY performance DESC
        LIMIT {limit} OFFSET {(page - 1) * limit}
        """
        with _rds.connect() as conn:
            result = conn.execute(query)
            results = result.fetchall()
        
        return [{"sector": row[0], "performance": row[1]} for row in results]

    except Exception as e:
        st.error(f"Failed to fetch sector performance: {e}")
        return []

# ----------------- Page Rendering -----------------
def page(rds=None, dynamo=None, **kwargs):
    """
    The 'Insights' page function that renders the insights using RDS data.
    """
    st.title("📊 Sector Insights")
    st.caption("View the top-performing sectors based on recent data.")
    
    # ----------------- Controls -----------------
    cols = st.columns(5)
    days = cols[0].selectbox("Range", options=[7, 30, 90], index=1)
    limit = cols[1].selectbox("Page size", options=[10, 20, 50], index=1)
    page = cols[2].number_input("Page", min_value=1, value=1, step=1)
    q = cols[3].text_input("Search", value="", placeholder="keyword…")
    source = cols[4].text_input("Source", value="", placeholder="e.g., Reuters")

    refresh = st.button("Refresh", use_container_width=False)
    if refresh:
        st.cache_data.clear()

    # ----------------- Fetch and Display Data -----------------
    sector_data = fetch_sector_performance(days, limit, page, rds)

    if not sector_data:
        st.info("No sector data available.")
        return

    # Prepare data for Plotly chart
    sectors = [item['sector'] for item in sector_data]
    performances = [item['performance'] for item in sector_data]

    # Create a bar chart using Plotly
    fig = go.Figure([go.Bar(
        x=sectors,
        y=performances,
        text=performances,
        textposition='auto',
        marker_color='royalblue',
        hovertemplate='Sector: %{x}<br>Performance: %{y}%',
    )])

    # Chart styling
    fig.update_layout(
        title="Top Performing Sectors",
        xaxis_title="Sector",
        yaxis_title="Performance (%)",
        template="plotly_white",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=40, t=40, b=40)
    )

    # Display the chart
    st.plotly_chart(fig, use_container_width=True)

    # ----------------- Download Section -----------------
    df = pd.DataFrame(sector_data)
    st.download_button(
        "📥 Download sector performance CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="sector_performance.csv",
        mime="text/csv",
    )
