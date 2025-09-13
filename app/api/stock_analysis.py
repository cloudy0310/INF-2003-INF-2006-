# app/api/stock_analysis.py
from typing import Optional, List
import os
import pandas as pd
from decimal import Decimal
import requests

# Optional: supabase client
try:
    from supabase import create_client
except Exception:
    create_client = None

# ---------- Supabase helpers ----------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE")

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
        # REST fallback
        url = f"{SUPABASE_URL}/rest/v1/financials"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        params = {"ticker": f"eq.{ticker}", "order": "period_end.desc"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
        return pd.DataFrame()

# ---------- Stock Prices ----------
def get_stock_prices(ticker: str, start: str = None, end: str = None) -> pd.DataFrame:
    """
    Fetch stock price history from 'stock_price' table
    start/end in 'YYYY-MM-DD' format
    """
    if create_client:
        sb = supabase_client()
        query = sb.table("stock_prices").select("*").eq("ticker", ticker)
        if start:
            query = query.gte("date", start)
        if end:
            query = query.lte("date", end)
        resp = query.order("date", desc=False).execute()
        data = resp.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    else:
        url = f"{SUPABASE_URL}/rest/v1/stock_price"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        filter_params = [f"ticker=eq.{ticker}"]
        if start:
            filter_params.append(f"date=gte.{start}")
        if end:
            filter_params.append(f"date=lte.{end}")
        params = {"select": "*", **{k:v for k,v in enumerate(filter_params)}}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
        return pd.DataFrame()
