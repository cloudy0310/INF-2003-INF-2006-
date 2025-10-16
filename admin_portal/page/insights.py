import pandas as pd
import streamlit as st
import plotly.express as px

def page(rds=None, dynamo=None):
    # Set up the Streamlit page configuration
    st.set_page_config(page_title="Market Insights", layout="wide")
    st.title("📊 Market Insights")
    st.caption("Top performing companies from recent financial data")

    if rds is None:
        st.error("RDS engine is required.")
        st.stop()

    # Optional filter for number of companies to display
    st.subheader("🔍 Company Performance Overview")
    col1, col2 = st.columns([1, 2])
    with col1:
        limit = st.slider("Number of companies to show", 5, 50, 20)

    try:
        # Query to get company performance data from 'companies' and 'financials' tables
        query = f"""
            SELECT 
                c.name AS company_name, 
                f.net_income
            FROM 
                companies c
            JOIN 
                financials f ON c.ticker = f.ticker
            WHERE 
                f.net_income IS NOT NULL  -- Filter out rows with NULL net_income
            ORDER BY 
                f.net_income DESC
            LIMIT {limit}
        """
        # Fetch data from the database
        df = pd.read_sql(query, rds)
    except Exception as e:
        st.warning("Company performance data not found — showing example chart instead.")
        st.exception(e)

        # Sample placeholder data in case of failure
        sample_data = {
            "company_name": ["Company A", "Company B", "Company C", "Company D", "Company E"],
            "net_income": [12.3, 8.7, -3.4, 5.9, 10.2]
        }
        df = pd.DataFrame(sample_data)

    # Check if the data is empty
    if df.empty:
        st.info("No company performance data found.")
        return

    # Create a bar chart to visualize the company performance
    fig = px.bar(
        df,
        x="company_name",
        y="net_income",  # Replace with your chosen performance column if different
        title=f"Top {limit} Companies by Performance",
        color="net_income",
        color_continuous_scale="Blues",
        labels={"company_name": "Company", "net_income": "Performance (Net Income)"},
    )

    fig.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_tickangle=-45
    )

    # Display the chart
    st.plotly_chart(fig, use_container_width=True)

    # Optionally show the raw data table
    with st.expander("🧾 Show raw data"):
        st.dataframe(df, use_container_width=True)
