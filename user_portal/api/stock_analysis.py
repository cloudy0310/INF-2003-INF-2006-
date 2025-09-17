from typing import Optional
import os
import pandas as pd
import requests

# Optional: supabase client
try:
    from supabase import create_client
except Exception:
    create_client = None

# ---------- Supabase helpers ----------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE")


def supabase_client():
    if create_client is None or SUPABASE_URL is None or SUPABASE_KEY is None:
        raise RuntimeError("Supabase client not configured")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------- Company Info ----------
def get_company_info(ticker: str) -> Optional[dict]:
    """
    Fetch company info from Supabase table 'companies'
    """
    if create_client:
        sb = supabase_client()
        resp = sb.table("companies").select("*").eq("ticker", ticker).execute()
        data = resp.data
        return data[0] if data else None
    else:
        # REST fallback
        if SUPABASE_URL is None or SUPABASE_KEY is None:
            return None
        url = f"{SUPABASE_URL}/rest/v1/companies"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        params = {"ticker": f"eq.{ticker}"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            res = r.json()
            return res[0] if res else None
        return None


# ---------- Financials ----------
def get_financials(ticker: str) -> pd.DataFrame:
    """
    Fetch financial statements from 'financials' table
    """
    if create_client:
        sb = supabase_client()
        resp = sb.table("financials").select("*").eq("ticker", ticker).order("period_end", desc=True).execute()
        data = resp.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    else:
        if SUPABASE_URL is None or SUPABASE_KEY is None:
            return pd.DataFrame()
        url = f"{SUPABASE_URL}/rest/v1/financials"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        params = {"ticker": f"eq.{ticker}", "order": "period_end.desc"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
        return pd.DataFrame()


# ---------- Stock Prices ----------
def _to_bool_series(s: pd.Series) -> pd.Series:
    """Robustly coerce a Series to boolean using common representations."""
    if s.dtype == "bool":
        return s.fillna(False)
    mapping = {
        True: True, 't': True, 'T': True, 'true': True, 'True': True, 'TRUE': True, '1': True, 1: True,
        False: False, 'f': False, 'F': False, 'false': False, 'False': False, '0': False, 0: False
    }
    return s.map(lambda v: mapping.get(v, False)).astype(bool)


def get_stock_prices(ticker: str, start: str = None, end: str = None, limit: int = 10000) -> pd.DataFrame:
    """
    Fetch stock prices for a ticker. Returns a DataFrame with:
      - date parsed to pd.Timestamp
      - numeric columns coerced
      - buy_signal / sell_signal as bool
      - sorted ascending by date (ready for plotting)
    Supports supabase client and REST fallback.
    """
    # --- Fetch data ---
    df = pd.DataFrame()
    if create_client:
        sb = supabase_client()
        query = sb.table("stock_prices").select("*").eq("ticker", ticker).order("date", desc=True)
        if start:
            query = query.gte("date", start)
        if end:
            query = query.lte("date", end)
        if limit:
            query = query.limit(limit)
        resp = query.execute()
        data = getattr(resp, "data", None)
        df = pd.DataFrame(data) if data else pd.DataFrame()
    else:
        if SUPABASE_URL is None or SUPABASE_KEY is None:
            raise RuntimeError("Supabase client not configured and REST credentials missing")
        url = f"{SUPABASE_URL}/rest/v1/stock_prices"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        params = {"ticker": f"eq.{ticker}", "order": "date.desc", "limit": str(limit)}
        if start:
            params["date"] = f"gte.{start}"
        if end:
            params["date"] = f"lte.{end}"
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        df = pd.DataFrame(r.json())

    if df.empty:
        return pd.DataFrame()

    # --- Normalize types ---
    # Parse date
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    # drop rows with invalid date
    df = df.dropna(subset=['date'])
    # Coerce numeric columns
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'bb_sma_20', 'bb_upper_20', 'bb_lower_20',
                    'rsi_14', 'macd', 'macd_signal', 'macd_hist']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop rows without valid OHLC (defensive) so latest_date is meaningful
    if all(c in df.columns for c in ['open', 'high', 'low', 'close']):
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
    # Ensure buy/sell columns exist and are boolean
    for col in ['buy_signal', 'sell_signal']:
        if col in df.columns:
            df[col] = _to_bool_series(df[col])
        else:
            df[col] = False

    # Sort ascending for plotting (older -> newer)
    df = df.sort_values('date').reset_index(drop=True)
    return df
