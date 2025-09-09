# run_all.py
import os
import argparse
from dotenv import load_dotenv
import pandas as pd

# load .env if present
load_dotenv()

from pipeline.utils import upsert_csv
from pipeline.fetch_companies import fetch_companies_and_officers
from pipeline.fetch_financials import fetch_financials_all
from pipeline.fetch_prices import fetch_prices_and_indicators
from pipeline.supabase_helpers import upsert_via_supabase, upsert_via_postgres

# defaults
OUT_DIR = os.environ.get("OUT_DIR", ".")
COMPANIES_CSV = os.path.join(OUT_DIR, "companies.csv")
OFFICERS_CSV = os.path.join(OUT_DIR, "company_officers.csv")
FINANCIALS_CSV = os.path.join(OUT_DIR, "financials.csv")
PRICES_CSV = os.path.join(OUT_DIR, "prices.csv")

# --- Helpers for type safety ---
def cast_numeric_columns(df: pd.DataFrame):
    """Automatically cast int-like and float-like columns."""
    df2 = df.copy()
    for col in df2.columns:
        if df2[col].dtype == object:
            try:
                df2[col] = pd.to_numeric(df2[col], errors='ignore')
            except Exception:
                continue
        # convert float columns that are actually integers
        if pd.api.types.is_float_dtype(df2[col]):
            if all(pd.isna(df2[col]) | (df2[col] % 1 == 0)):
                df2[col] = df2[col].astype('Int64')
    return df2

def ensure_columns(df: pd.DataFrame, expected: list):
    for c in expected:
        if c not in df.columns:
            df[c] = None
    return df[expected]

# --- Main pipeline ---
def run_pipeline(tickers, start, write_csv=True, push_db=False, db_method="supabase"):
    print("Starting pipeline for:", tickers)

    # 1) Companies & Officers
    comp_df, off_df = fetch_companies_and_officers(tickers)
    comp_expected = ["ticker","name","short_name","exchange","market","country","region","city","address1","phone",
                     "website","ir_website","sector","industry","industry_key","long_business_summary",
                     "full_time_employees","founded_year","market_cap","float_shares","shares_outstanding",
                     "beta","book_value","dividend_rate","dividend_yield","last_dividend_date","last_split_date",
                     "last_split_factor","logo_url","esg_populated","created_at","updated_at","raw_yfinance"]
    comp_df = ensure_columns(comp_df, comp_expected)

    if write_csv:
        upsert_csv(comp_df, COMPANIES_CSV, key_subset=["ticker"], sort_cols=["updated_at"])

    officers_expected = ["ticker","name","title","year_of_birth","age","fiscal_year","total_pay","extra","created_at"]
    if not off_df.empty:
        off_df = ensure_columns(off_df, officers_expected)
        off_df = cast_numeric_columns(off_df)
        if write_csv:
            upsert_csv(off_df, OFFICERS_CSV, key_subset=["ticker","name","title"], sort_cols=["created_at"])
    else:
        print("No officers fetched.")

    # 2) Financials
    fin_df = fetch_financials_all(tickers)
    fin_expected = ["ticker","period_end","period_type","reported_currency",
                    "revenue","cost_of_revenue","gross_profit","operating_income","net_income","eps_basic",
                    "eps_diluted","ebitda","gross_margin","operating_margin","ebitda_margin","net_profit_margin",
                    "total_assets","total_liabilities","total_equity","cash_and_equivalents","total_debt",
                    "operating_cashflow","capital_expenditures","free_cash_flow","shares_outstanding","shares_float",
                    "market_cap","price_to_earnings","forward_pe","peg_ratio","revenue_growth","earnings_growth",
                    "number_of_analysts","recommendation_mean","fetched_at","raw_json"]
    if not fin_df.empty:
        fin_df = ensure_columns(fin_df, fin_expected)
        fin_df = cast_numeric_columns(fin_df)
        if write_csv:
            upsert_csv(fin_df, FINANCIALS_CSV, key_subset=["ticker","period_end","period_type"], sort_cols=["fetched_at"])
    else:
        print("No financials fetched.")

    # 3) Prices
    prices_df = fetch_prices_and_indicators(tickers, start=start)
    price_expected = ["ticker","date","open","high","low","close","volume","bb_sma_20","bb_upper_20",
                      "bb_lower_20","rsi_14","macd","macd_signal","macd_hist","buy_signal","sell_signal"]
    if not prices_df.empty:
        prices_df = ensure_columns(prices_df, price_expected)
        prices_df = cast_numeric_columns(prices_df)
        if write_csv:
            upsert_csv(prices_df, PRICES_CSV, key_subset=["ticker","date"], sort_cols=["date"])
    else:
        print("No prices fetched.")

    # 4) Push to DB
    if push_db:
        db_method = db_method.lower()
        if db_method == "supabase":
            SUPABASE_URL = os.environ.get("SUPABASE_URL")
            SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE")
            if not SUPABASE_URL or not SUPABASE_KEY:
                raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE required for supabase push.")

            if not comp_df.empty:
                upsert_via_supabase(comp_df, "companies", SUPABASE_URL, SUPABASE_KEY, json_columns=["raw_yfinance"])
            if not off_df.empty:
                upsert_via_supabase(off_df, "company_officers", SUPABASE_URL, SUPABASE_KEY)
            if not fin_df.empty:
                upsert_via_supabase(fin_df, "financials", SUPABASE_URL, SUPABASE_KEY, json_columns=["raw_json"])
            """ if not prices_df.empty:
                upsert_via_supabase(prices_df, "prices", SUPABASE_URL, SUPABASE_KEY) """

        elif db_method == "postgres":
            pg_conn = os.environ.get("PG_CONN")  # optional connection string
            if not comp_df.empty:
                upsert_via_postgres(comp_df, "companies", ["ticker"], pg_conn=pg_conn)
            if not off_df.empty:
                upsert_via_postgres(off_df, "company_officers", ["ticker","name","title"], pg_conn=pg_conn)
            if not fin_df.empty:
                upsert_via_postgres(fin_df, "financials", ["ticker","period_end","period_type"], pg_conn=pg_conn)
            """ if not prices_df.empty:
                upsert_via_postgres(prices_df, "prices", ["ticker","date"], pg_conn=pg_conn) """
        else:
            raise RuntimeError(f"Unsupported db_method: {db_method}")

    print("Pipeline run complete.")

# --- CLI ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default=os.environ.get("TICKERS", "AAPL,MSFT,AMZN"))
    parser.add_argument("--start", default=os.environ.get("START", "2010-01-01"))
    parser.add_argument("--out", default=os.environ.get("OUT_DIR", "."))
    parser.add_argument("--no-csv", dest="write_csv", action="store_false")
    parser.add_argument("--push-db", dest="push_db", action="store_true")
    parser.add_argument("--db-method", default=os.environ.get("DB_METHOD", "supabase"), choices=["supabase","postgres"])
    args = parser.parse_args()

    OUT_DIR = args.out
    os.environ["OUT_DIR"] = OUT_DIR

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    run_pipeline(tickers, start=args.start, write_csv=args.write_csv, push_db=args.push_db, db_method=args.db_method)
