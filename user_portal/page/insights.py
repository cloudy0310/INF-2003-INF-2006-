import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
import os

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE")

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def page():
    st.set_page_config(page_title="Market Insights", layout="wide")
    st.title("📊 Market Insights")
    st.caption("Top performing companies based on recent financial data")

    if supabase is None:
        st.error("Supabase client is not initialized.")
        st.stop()

    # Filters
    st.subheader("🔍 Company Performance Overview")
    limit = st.slider("Number of companies to show", 5, 50, 20)

    # -------------------------------
    # 1. Fetch financials (net income)
    # -------------------------------
    try:
        financials_resp = (
            supabase.table("financials")
            .select("ticker, net_income")
            .order("net_income", desc=True)
            .limit(limit)
            .execute()
        )

        financials_df = pd.DataFrame(financials_resp.data)

    except Exception as e:
        st.error("Failed to fetch financial data.")
        st.exception(e)
        return

    # Handle empty data
    if financials_df.empty:
        st.info("No financial data available.")
        return

    # -------------------------------
    # 2. Fetch company names
    # -------------------------------
    tickers = financials_df["ticker"].tolist()

    companies_resp = (
        supabase.table("companies")
        .select("ticker, name")
        .in_("ticker", tickers)
        .execute()
    )

    companies_df = pd.DataFrame(companies_resp.data)

    # -------------------------------
    # 3. Merge companies + financials
    # -------------------------------
    df = financials_df.merge(companies_df, on="ticker", how="left")

    # Rename for plotting
    df = df.rename(columns={"name": "company_name"})

    # -------------------------------
    # 4. Plot chart
    # -------------------------------
    fig = px.bar(
        df,
        x="company_name",
        y="net_income",
        title=f"Top {limit} Companies by Net Income",
        color="net_income",
        color_continuous_scale="Blues",
        labels={
            "company_name": "Company",
            "net_income": "Net Income",
        },
    )

    fig.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_tickangle=-45
    )

    st.plotly_chart(fig, use_container_width=True)

    # -------------------------------
    # Show raw data
    # -------------------------------
    with st.expander("🧾 Show raw data"):
        st.dataframe(df, use_container_width=True)
