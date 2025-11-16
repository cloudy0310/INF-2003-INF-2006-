# insights.py
from supabase import create_client, Client
import os

# Replace with your Supabase URL and key
SUPABASE_URL = os.environ.get("SUPABASE_URL") or "https://your-project.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "your-anon-or-service-role-key"

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_financials(ticker: str):
    """
    Fetch financial records for a given ticker.
    Returns a list of dictionaries.
    """
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
            # Safely convert numeric fields
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
                        record[field] = None  # Ensure PostgreSQL-friendly numeric value
                safe_data.append(record)

            return safe_data
        else:
            print(f"No financial records found for {ticker}")
            return []

    except Exception as e:
        print("Failed to fetch financial data from Supabase.")
        print("Error:", e)
        return []

if __name__ == "__main__":
    ticker_input = input("Enter ticker symbol (e.g., AAPL): ").upper()
    financials = fetch_financials(ticker_input)

    if financials:
        print(f"\nLatest financials for {ticker_input}:")
        for record in financials:
            print(record)
    else:
        print("No data to display.")
