import pandas as pd
import streamlit as st
import plotly.express as px

def page(rds=None):
    st.set_page_config(page_title="Market Insights", layout="wide")
    st.title("📊 Market Insights")
    st.caption("Top performing sectors from recent data")

    # Placeholder for number of sectors to show
    st.subheader("🔍 Sector Performance Overview")
    col1, col2 = st.columns([1, 2])
    with col1:
        limit = st.slider("Number of sectors to show", 5, 50, 20)

    # Sample placeholder data (as fallback for now)
    sample_data = {
        "sector": ["Tech", "Finance", "Energy", "Healthcare", "Real Estate"],
        "performance": [12.3, 8.7, -3.4, 5.9, 10.2]
    }

    df = pd.DataFrame(sample_data)
    
    # Bar chart for performance
    fig = px.bar(df, x="sector", y="performance", title=f"Top {limit} Sector Performances")
    st.plotly_chart(fig, use_container_width=True)

    # Display raw data in an expandable section
    with st.expander("🧾 Show raw data"):
        st.dataframe(df, use_container_width=True)
