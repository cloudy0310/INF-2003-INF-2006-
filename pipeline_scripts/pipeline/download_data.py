"""
Centralized ETL: fetch companies, officers, financials and prices for a list of tickers,
write to CSV files and upsert (update duplicates) based on natural keys.

Usage:
  - Edit TICKERS below (or load from a file)
  - python run_all.py
"""

import os
import json
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf

# ---------- CONFIG ----------
TICKERS = ["AAPL", "MSFT", "AMZN"]   # <-- edit tickers here (or load from file)
START = "2010-01-01"                 # price history start date
OUT_DIR = "."                        # where CSVs will be written (change if needed)

COMPANIES_CSV = os.path.join(OUT_DIR, "companies.csv")
OFFICERS_CSV = os.path.join(OUT_DIR, "company_officers.csv")
FINANCIALS_CSV = os.path.join(OUT_DIR, "financials.csv")
PRICES_CSV = os.path.join(OUT_DIR, "prices.csv")

# ---------- HELPERS ----------
def to_json_text(obj):
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return None

def safe_get(info, *keys):
    for k in keys:
        if isinstance(info, dict) and k in info:
            return info[k]
    return None

def ensure_dir_for_file(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

# ---------- FETCH / BUILD ROWS ----------
def fetch_companies_and_officers(tickers):
    companies_rows = []
    officers_rows = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
        except Exception as e:
            print(f"[companies] failed ticker {t}: {e}")
            info = {}

        row = {
            "ticker": t,
            "name": info.get("longName") or info.get("shortName"),
            "short_name": info.get("shortName"),
            "exchange": info.get("exchange"),
            "market": info.get("market"),
            "country": info.get("country"),
            "region": info.get("region"),
            "city": info.get("city"),
            "address1": info.get("address1"),
            "phone": info.get("phone"),
            "website": info.get("website"),
            "ir_website": info.get("irWebsite"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "industry_key": info.get("industryKey"),
            "long_business_summary": info.get("longBusinessSummary"),
            "full_time_employees": info.get("fullTimeEmployees"),
            "founded_year": info.get("founded"),    # may be None
            "market_cap": info.get("marketCap"),
            "float_shares": info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "beta": info.get("beta"),
            "book_value": info.get("bookValue"),
            "dividend_rate": info.get("dividendRate"),
            "dividend_yield": info.get("dividendYield"),
            "last_dividend_date": (pd.to_datetime(info.get("lastDividendDate"), unit='s').date().isoformat()
                                   if isinstance(info.get("lastDividendDate"), (int, float)) else None) if info.get("lastDividendDate") else None,
            "last_split_date": (pd.to_datetime(info.get("lastSplitDate"), unit='s').date().isoformat()
                                if isinstance(info.get("lastSplitDate"), (int, float)) else None) if info.get("lastSplitDate") else None,
            "last_split_factor": info.get("lastSplitFactor"),
            "logo_url": info.get("logo_url") or info.get("logo"),
            "esg_populated": info.get("esgPopulated"),
            "created_at": pd.Timestamp.now().isoformat(),
            "updated_at": pd.Timestamp.now().isoformat(),
            "raw_yfinance": to_json_text(info),
        }
        companies_rows.append(row)

        # Officers: yfinance stores as list under 'companyOfficers' (or similar)
        officers = info.get("companyOfficers") or []
        for off in officers:
            officers_rows.append({
                "ticker": t,
                "name": off.get("name"),
                "title": off.get("title"),
                "year_of_birth": off.get("yearBorn"),
                "age": off.get("age"),
                "fiscal_year": off.get("fiscalYear"),
                "total_pay": off.get("totalPay"),
                "extra": to_json_text({k: off.get(k) for k in off.keys() if k not in ["name","title","yearBorn","age","fiscalYear","totalPay"]}),
                "created_at": pd.Timestamp.now().isoformat()
            })

    comp_df = pd.DataFrame(companies_rows)
    off_df = pd.DataFrame(officers_rows)
    return comp_df, off_df

def fetch_financials_all(tickers):
    # returns DataFrame with canonical columns that match financials.sql
    rows = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            # yfinance dataframes (income, balance, cashflow)
            fin = tk.financials    # income
            bal = tk.balance_sheet
            cf = tk.cashflow
        except Exception as e:
            print(f"[financials] failed ticker {t}: {e}")
            fin, bal, cf = None, None, None

        # Helper: convert df to dict keyed by period_end
        def df_period_dict(df):
            out = {}
            if df is None or df.empty:
                return out
            for col in df.columns:
                period_key = pd.to_datetime(col).date().isoformat()
                # convert the column to a simple dict
                s = df[col].to_dict()
                # normalize NaN to None
                s = {k: (None if pd.isna(v) else v) for k, v in s.items()}
                out[period_key] = s
            return out

        fin_map = df_period_dict(fin)
        bal_map = df_period_dict(bal)
        cf_map = df_period_dict(cf)

        all_periods = sorted(set(list(fin_map.keys()) + list(bal_map.keys()) + list(cf_map.keys())))
        if not all_periods:
            # fallback: attempt to use 'mostRecentQuarter' or 'mostRecentQuarter' from info
            info = getattr(tk, "info", {}) or {}
            mrq = info.get("mostRecentQuarter")
            if mrq:
                try:
                    pd.to_datetime(mrq)
                    all_periods = [pd.to_datetime(mrq).date().isoformat()]
                except Exception:
                    pass

        for p in all_periods:
            fin_r = fin_map.get(p, {})
            bal_r = bal_map.get(p, {})
            cf_r = cf_map.get(p, {})

            # map common names (these vary by ticker / yfinance version)
            row = {
                "ticker": t,
                "period_end": p,
                "period_type": "FY",  # assume annual when coming from .financials; adjust if you parse quarterals
                "reported_currency": None,

                # income
                "revenue": fin_r.get("Total Revenue") or fin_r.get("TotalRevenue") or fin_r.get("Revenue") or fin_r.get("totalRevenue"),
                "cost_of_revenue": fin_r.get("Cost of Revenue") or fin_r.get("CostOfRevenue") or fin_r.get("costOfRevenue"),
                "gross_profit": fin_r.get("Gross Profit") or fin_r.get("GrossProfit") or fin_r.get("grossProfit"),
                "operating_income": fin_r.get("Operating Income") or fin_r.get("OperatingIncome") or fin_r.get("OperatingLoss"),
                "net_income": fin_r.get("Net Income") or fin_r.get("NetIncome") or fin_r.get("Net Income Applicable To Common Shares"),
                "eps_basic": fin_r.get("Basic EPS") or fin_r.get("Net income per share basic"),
                "eps_diluted": fin_r.get("Diluted EPS") or fin_r.get("Net income per share diluted"),
                "ebitda": fin_r.get("EBITDA") or fin_r.get("Ebitda"),

                # margins (often available as separate fields; else left null)
                "gross_margin": fin_r.get("Gross Margin") or fin_r.get("grossMargins"),
                "operating_margin": fin_r.get("Operating Margin") or fin_r.get("operatingMargins"),
                "ebitda_margin": fin_r.get("EBITDA Margin") or fin_r.get("ebitdaMargins"),
                "net_profit_margin": fin_r.get("Net Profit Margin") or fin_r.get("profitMargins"),

                # balance sheet
                "total_assets": bal_r.get("Total Assets") or bal_r.get("totalAssets"),
                "total_liabilities": bal_r.get("Total Liab") or bal_r.get("TotalLiab") or bal_r.get("totalLiabilities"),
                "total_equity": bal_r.get("Total Stockholder's Equity") or bal_r.get("Total stockholder equity") or bal_r.get("totalStockholderEquity"),
                "cash_and_equivalents": bal_r.get("Cash And Cash Equivalents") or bal_r.get("cashAndShortTermInvestments"),
                "total_debt": bal_r.get("Total Debt") or bal_r.get("totalDebt"),

                # cashflow
                "operating_cashflow": cf_r.get("Total Cash From Operating Activities") or cf_r.get("totalCashFromOperatingActivities"),
                "capital_expenditures": cf_r.get("Capital Expenditures") or cf_r.get("capitalExpenditure"),
                "free_cash_flow": None,

                # market/per-share placeholders
                "shares_outstanding": None,
                "shares_float": None,
                "market_cap": None,
                "price_to_earnings": None,
                "forward_pe": None,
                "peg_ratio": None,

                "revenue_growth": None,
                "earnings_growth": None,

                "number_of_analysts": None,
                "recommendation_mean": None,

                "fetched_at": pd.Timestamp.now().isoformat(),
                "raw_json": to_json_text({"income": fin_r, "balance": bal_r, "cashflow": cf_r})
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df

def fetch_prices_and_indicators(tickers, start=START):
    all_rows = []
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(start=start, auto_adjust=False)
            if hist is None or hist.empty:
                print(f"[prices] no history for {t}")
                continue
            df = hist.reset_index().rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            # ensure date col is normalized str Y-m-d
            df["date"] = pd.to_datetime(df["Date"] if "Date" in df.columns else df["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"[prices] failed ticker {t}: {e}")
            continue

        # compute indicators
        df["bb_sma_20"] = df["close"].rolling(window=20, min_periods=1).mean()
        df["bb_std_20"] = df["close"].rolling(window=20, min_periods=1).std().fillna(0)
        df["bb_upper_20"] = df["bb_sma_20"] + 2 * df["bb_std_20"]
        df["bb_lower_20"] = df["bb_sma_20"] - 2 * df["bb_std_20"]

        # RSI(14)
        delta = df["close"].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        roll_up = up.rolling(14, min_periods=1).mean()
        roll_down = down.rolling(14, min_periods=1).mean().replace(0, np.nan)
        rs = roll_up / roll_down
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        df["buy_signal"] = ((df["rsi_14"] < 30) & (df["macd"] > df["macd_signal"])).astype(bool)
        df["sell_signal"] = ((df["rsi_14"] > 70) & (df["macd"] < df["macd_signal"])).astype(bool)

        # columns to output and add ticker
        out = df.reset_index(drop=True)
        out["ticker"] = t
        # ensure columns exist in consistent order
        cols = ["ticker", "date", "open", "high", "low", "close", "volume",
                "bb_sma_20", "bb_upper_20", "bb_lower_20", "rsi_14",
                "macd", "macd_signal", "macd_hist", "buy_signal", "sell_signal"]
        # some columns may have alternative names; create missing ones as NaN
        for c in cols:
            if c not in out.columns:
                out[c] = np.nan
        out = out[cols]
        all_rows.append(out)

    if all_rows:
        result = pd.concat(all_rows, ignore_index=True)
    else:
        result = pd.DataFrame(columns=["ticker","date","open","high","low","close","volume",
                                       "bb_sma_20","bb_upper_20","bb_lower_20","rsi_14",
                                       "macd","macd_signal","macd_hist","buy_signal","sell_signal"])
    return result

# ---------- UPSERT (CSV merge) ----------
def upsert_csv(df_new, csv_path, key_subset, sort_cols=None):
    """
    Upsert DataFrame into csv_path by merging with existing CSV (if exists),
    dropping duplicates according to key_subset (keeping the last row).
    - key_subset: list of column names that form uniqueness key
    """
    ensure_dir_for_file(csv_path)
    if os.path.exists(csv_path):
        try:
            df_existing = pd.read_csv(csv_path, dtype=str)
            # convert new to same dtypes where possible
            # combine
            df_combined = pd.concat([df_existing, df_new.astype(str)], ignore_index=True, sort=False)
        except Exception as e:
            print(f"[upsert] failed reading existing csv {csv_path}: {e}")
            df_combined = df_new
    else:
        df_combined = df_new

    # normalize column order: ensure all columns from both are present
    # drop duplicates: keep last (so new rows override old)
    if all(col in df_combined.columns for col in key_subset):
        df_combined = df_combined.drop_duplicates(subset=key_subset, keep="last")
    else:
        # if key subset not present, just drop exact duplicate rows
        df_combined = df_combined.drop_duplicates(keep="last")

    # optionally sort
    if sort_cols:
        present_sort = [c for c in sort_cols if c in df_combined.columns]
        if present_sort:
            df_combined = df_combined.sort_values(by=present_sort, ascending=False)

    # write back
    df_combined.to_csv(csv_path, index=False)
    print(f"[upsert] wrote {csv_path} ({len(df_combined)} rows)")

# ---------- MAIN ----------
def main():
    print("Starting centralized ETL for tickers:", TICKERS)

    # 1) Companies & officers
    print("Fetching companies and officers...")
    companies_df, officers_df = fetch_companies_and_officers(TICKERS)
    # Ensure columns exactly match targets (coerce columns to those names; missing columns will be created)
    companies_expected = ["ticker","name","short_name","exchange","market","country","region","city","address1","phone","website","ir_website",
                          "sector","industry","industry_key","long_business_summary","full_time_employees","founded_year","market_cap","float_shares",
                          "shares_outstanding","beta","book_value","dividend_rate","dividend_yield","last_dividend_date","last_split_date","last_split_factor",
                          "logo_url","esg_populated","created_at","updated_at","raw_yfinance"]
    for c in companies_expected:
        if c not in companies_df.columns:
            companies_df[c] = None
    companies_df = companies_df[companies_expected]
    upsert_csv(companies_df, COMPANIES_CSV, key_subset=["ticker"], sort_cols=["updated_at"])

    # officers
    if not officers_df.empty:
        officers_expected = ["ticker","name","title","year_of_birth","age","fiscal_year","total_pay","extra","created_at"]
        for c in officers_expected:
            if c not in officers_df.columns:
                officers_df[c] = None
        officers_df = officers_df[officers_expected]
        upsert_csv(officers_df, OFFICERS_CSV, key_subset=["ticker","name","title"], sort_cols=["created_at"])
    else:
        print("No officers fetched.")

    # 2) Financials
    print("Fetching financials...")
    fin_df = fetch_financials_all(TICKERS)
    if not fin_df.empty:
        # ensure expected columns exist and proper ordering
        fin_expected = ["ticker","period_end","period_type","reported_currency",
                        "revenue","cost_of_revenue","gross_profit","operating_income","net_income","eps_basic","eps_diluted","ebitda",
                        "gross_margin","operating_margin","ebitda_margin","net_profit_margin",
                        "total_assets","total_liabilities","total_equity","cash_and_equivalents","total_debt",
                        "operating_cashflow","capital_expenditures","free_cash_flow",
                        "shares_outstanding","shares_float","market_cap","price_to_earnings","forward_pe","peg_ratio",
                        "revenue_growth","earnings_growth","number_of_analysts","recommendation_mean","fetched_at","raw_json"]
        for c in fin_expected:
            if c not in fin_df.columns:
                fin_df[c] = None
        fin_df = fin_df[fin_expected]
        upsert_csv(fin_df, FINANCIALS_CSV, key_subset=["ticker","period_end","period_type"], sort_cols=["fetched_at"])
    else:
        print("No financials fetched.")

    # 3) Prices + indicators (single aggregated prices.csv with ticker column)
    print("Fetching prices and indicators...")
    prices_df = fetch_prices_and_indicators(TICKERS, start=START)
    if not prices_df.empty:
        # ensure correct dtypes / column order
        price_expected = ["ticker","date","open","high","low","close","volume","bb_sma_20","bb_upper_20","bb_lower_20","rsi_14",
                          "macd","macd_signal","macd_hist","buy_signal","sell_signal"]
        for c in price_expected:
            if c not in prices_df.columns:
                prices_df[c] = None
        prices_df = prices_df[price_expected]
        upsert_csv(prices_df, PRICES_CSV, key_subset=["ticker","date"], sort_cols=["date"])
    else:
        print("No prices fetched.")

    print("ETL finished.")

if __name__ == "__main__":
    main()
