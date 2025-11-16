from supabase import create_client, Client
import streamlit as st
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://your-project.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "your-anon-or-service-role-key"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_financials(ticker: str):
    try:
        response = (
            supabase
            .table("financials")
            .select("*")
            .eq("ticker", ticker)
            .order("period_end", desc=True)
            .limit(5)
            .execute()
        )

        if response.data:
            safe_data = []
            numeric_fields = [
                "revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income",
                "eps_basic", "eps_diluted", "ebitda", "gross_margin", "operating_margin",
                "ebitda_margin", "net_profit_margin", "total_assets", "total_liabilities",
                "total_equity", "cash_and_equivalents", "total_debt", "operating_cashflow",
                "capital_expenditures", "free_cash_flow", "shares_outstanding", "shares_float",
                "market_cap", "price_to_earnings", "forward_pe", "peg_ratio", "revenue_growth",
                "earnings_growth", "recommendation_mean"
            ]

            for record in response.data:
                for field in numeric_fields:
                    if field in record and (record[field] is None or str(record[field]).lower() == "none"):
                        record[field] = None
                safe_data.append(record)

            return safe_data
        else:
            return []
    except Exception as e:
        st.error(f"Failed to fetch financial data: {e}")
        return []

# This is the page function Streamlit will call
def page(**kwargs):
    st.title("Financial Insights")

    ticker_input = st.text_input("Enter ticker symbol (e.g., AAPL)").upper()
    if ticker_input:
        financials = fetch_financials(ticker_input)
        if financials:
            st.subheader(f"Latest financials for {ticker_input}")
            for record in financials:
                st.json(record)
        else:
            st.warning("No financial data found.")
