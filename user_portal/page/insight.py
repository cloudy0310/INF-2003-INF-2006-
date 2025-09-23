import streamlit as st
import pandas as pd
from supabase import Client

def page(supabase: Client = None):
    if supabase is None:
        st.error("Supabase client missing.")
        return
    
    # Your complex SQL analysis logic here
    st.title("🔍 Advanced SQL Analysis")

    # Call the function for complex SQL (e.g., top performers by sector)
    _top_performers_by_sector(supabase)

def _top_performers_by_sector(supabase: Client):
    # SQL query to find top 3 companies by market cap in each sector
    query = """
        WITH ranked_companies AS (
            SELECT
                c.ticker,
                c.name AS company_name,
                c.market_cap,
                c.sector,
                RANK() OVER (PARTITION BY c.sector ORDER BY c.market_cap DESC) AS rank
            FROM companies c
            JOIN financials f ON c.ticker = f.ticker
            WHERE f.period_end = (SELECT MAX(period_end) FROM financials WHERE ticker = c.ticker)
        )
        SELECT
            ticker,
            company_name,
            market_cap,
            sector
        FROM ranked_companies
        WHERE rank <= 3
        ORDER BY sector, rank;
    """

    try:
        data = supabase.rpc("run_sql", {"sql": query}).execute()

        if not data or len(data['data']) == 0:
            st.warning("No data found for top performers.")
            return

        # Convert to DataFrame for display
        df = pd.DataFrame(data['data'])
        st.write("### Top 3 Performers by Sector")
        st.dataframe(df)

    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
