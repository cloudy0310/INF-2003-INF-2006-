# insights.py

import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from dotenv import load_dotenv
import os

# -------------------------------
# 1️⃣ Load environment variables
# -------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")  # Use your anon key

# -------------------------------
# 2️⃣ Create Supabase client
# -------------------------------
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------
# 3️⃣ Streamlit page
# -------------------------------
def page(supabase=None):
    """
    Display Market Insights page.

    Parameters:
    supabase: optional Supabase client. If not provided, will use the global client.
    """
    st.set_page_config(page_title="Market Insights", layout="wide")
    st.title("📊 Market Insights")
    st.caption("Top performing companies based on recent financial data")

    # Use the passed supabase client or fallback to the one we created
    client = supabase or globals().get("supabase")
    if client is None:
        st.error("Supabase client is not initialized.")
        st.stop()

    # -------------------------------
    # Filter: number of companies to display
    # -------------------------------
    st.subheader("🔍 Company Performance Overview")
    limit = st.slider("Number of companies to show", 5, 50, 20)

    # -------------------------------
    # Fetch financials
    # -------------------------------
    try:
        financials_resp = (
            client.table("financials")
            .select("ticker, net_income, period_end")
            .filter("net_income", "not.is", "null")  # Correct NOT NULL filter
            .order("period_end", desc=True)
            .limit(limit * 2)
            .execute()
        )


        financials_df = pd.DataFrame(financials_resp.data)

        if financials_df.empty:
            st.info("No financial data available.")
            return

        # Keep only top 'limit' after removing missing net_income
        financials_df = financials_df[financials_df["net_income"].notnull()]
        financials_df = financials_df.head(limit)

    except Exception as e:
        st.error("Failed to fetch financial data from Supabase.")
        st.exception(e)
        return

    # -------------------------------
    # Fetch company names
    # -------------------------------
    tickers = financials_df["ticker"].tolist()
    try:
        companies_resp = (
            client.table("companies")
            .select("ticker, name")
            .in_("ticker", tickers)
            .execute()
        )
        companies_df = pd.DataFrame(companies_resp.data)
    except Exception as e:
        st.warning("Failed to fetch company names.")
        st.exception(e)
        companies_df = pd.DataFrame({"ticker": tickers, "name": tickers})  # fallback

    # -------------------------------
    # Merge financials + company names
    # -------------------------------
    df = financials_df.merge(companies_df, on="ticker", how="left")
    df = df.rename(columns={"name": "company_name"})

    # -------------------------------
    # Plot bar chart
    # -------------------------------
    fig = px.bar(
        df,
        x="company_name",
        y="net_income",
        title=f"Top {len(df)} Companies by Net Income",
        color="net_income",
        color_continuous_scale="Blues",
        labels={"company_name": "Company", "net_income": "Net Income"},
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


# -------------------------------
# 4️⃣ Run page if called directly
# -------------------------------
if __name__ == "__main__":
    page()
