#!/usr/bin/env python3
# etl/fetch_companies.py
from __future__ import annotations
import os, json
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

# Optional libs
try:
    import psycopg2
    import psycopg2.extras as pg_extras
except Exception:
    psycopg2 = None
    pg_extras = None

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    import requests
except Exception:
    requests = None

# ---------------- helpers ----------------
DEFAULT_TICKERS = os.environ.get("TICKERS",
    "AAPL,META,AMZN,NVDA,MSFT,NIO,XPEV,LI,ZK,PYPL,AXP,MA,GPN,V,FUTU,HOOD,TIGR,IBKR,GS,JPM,BLK,C,BX,KO,WMT,MCD,NKE,SBUX,COIN,BCS,AMD,BABA,PINS,BA,AVGO,JD,PDD,SNAP,FVRR,DJT,SHOP,SE"
)

def to_iso_date(v) -> Optional[str]:
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return pd.to_datetime(v, unit="s").date().isoformat()
        return pd.to_datetime(v).date().isoformat()
    except Exception:
        return None

def safe_decimal(x, ndigits: int = 2) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        quant = Decimal("1." + "0"*ndigits)
        return Decimal(str(x)).quantize(quant)
    except Exception:
        try:
            return Decimal(str(float(x))).quantize(quant)
        except Exception:
            return None

def chunked(iterable, size=200):
    it = iter(iterable)
    while True:
        chunk = []
        try:
            for _ in range(size):
                chunk.append(next(it))
        except StopIteration:
            if chunk: yield chunk
            break
        yield chunk

# ---------------- fetch ----------------
def fetch_companies(tickers: List[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        t = t.strip().upper()
        if not t: 
            continue
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
        except Exception as e:
            print(f"[fetch_companies] {t} error: {e}")
            info = {}

        rows.append({
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
            "full_time_employees": int(info.get("fullTimeEmployees")) if info.get("fullTimeEmployees") not in (None, float("nan")) else None,
            "founded_year": int(info.get("founded")) if info.get("founded") not in (None, float("nan")) else None,
            "market_cap": safe_decimal(info.get("marketCap"), ndigits=2),
            "float_shares": int(info.get("floatShares")) if info.get("floatShares") not in (None, float("nan")) else None,
            "shares_outstanding": int(info.get("sharesOutstanding")) if info.get("sharesOutstanding") not in (None, float("nan")) else None,
            "beta": safe_decimal(info.get("beta"), ndigits=6),
            "book_value": safe_decimal(info.get("bookValue"), ndigits=6),
            "dividend_rate": safe_decimal(info.get("dividendRate"), ndigits=8),
            "dividend_yield": safe_decimal(info.get("dividendYield"), ndigits=8),
            "last_dividend_date": to_iso_date(info.get("lastDividendDate")),
            "last_split_date": to_iso_date(info.get("lastSplitDate")),
            "last_split_factor": info.get("lastSplitFactor"),
            "logo_url": info.get("logo") or info.get("logo_url"),
            "esg_populated": bool(info.get("esgPopulated")) if info.get("esgPopulated") is not None else None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            # store raw info as dict for JSONB
            "raw_yfinance": info if isinstance(info, dict) else {}
        })
    df = pd.DataFrame(rows)
    return df

# ---------------- Postgres upsert ----------------
def pg_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 required for RDS mode")
    return psycopg2.connect(
        host=os.environ.get("PG_HOST"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB"),
        user=os.environ.get("PG_USER"),
        password=os.environ.get("PG_PASS"),
        connect_timeout=10
    )

def pg_upsert_companies(conn, df: pd.DataFrame):
    if df is None or df.empty:
        print("[pg] no companies to upsert")
        return
    cols = [
        "ticker","name","short_name","exchange","market","country","region","city","address1","phone","website","ir_website",
        "sector","industry","industry_key","long_business_summary","full_time_employees","founded_year","market_cap","float_shares",
        "shares_outstanding","beta","book_value","dividend_rate","dividend_yield","last_dividend_date","last_split_date",
        "last_split_factor","logo_url","esg_populated","created_at","updated_at","raw_yfinance"
    ]
    # ensure columns present & order
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    values = []
    for _, r in df.iterrows():
        rowvals = []
        for c in cols:
            v = r[c]
            if pd.isna(v):
                rowvals.append(None)
            elif isinstance(v, (dict, list)):
                rowvals.append(pg_extras.Json(v))
            elif isinstance(v, Decimal):
                rowvals.append(v)
            else:
                rowvals.append(v)
        values.append(tuple(rowvals))

    # build SQL
    col_sql = ",".join(f'"{c}"' for c in cols)
    template = "(" + ",".join(["%s"] * len(cols)) + ")"
    update_cols = [c for c in cols if c != "ticker"]
    set_sql = ",".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
    sql = f'INSERT INTO companies ({col_sql}) VALUES %s ON CONFLICT (ticker) DO UPDATE SET {set_sql};'

    with conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, values, template=template)
    conn.commit()
    print(f"[pg] upserted {len(values)} companies")

# ---------------- Supabase upsert (client + REST fallback) ----------------
def supabase_upsert(df: pd.DataFrame, table: str, url: str, key: str, on_conflict: str = "ticker"):
    if df is None or df.empty:
        print("[supabase] no companies to upsert")
        return
    records = df.to_dict(orient="records")
    def norm(r):
        nr = {}
        for k, v in r.items():
            if pd.isna(v):
                nr[k] = None
            elif isinstance(v, (dict, list)):
                nr[k] = v
            elif isinstance(v, Decimal):
                nr[k] = float(v)
            else:
                nr[k] = v
        return nr
    payloads = [norm(r) for r in records]
    chunk_size = 200
    for i in range(0, len(payloads), chunk_size):
        chunk = payloads[i:i+chunk_size]
        if create_client is not None:
            try:
                sb = create_client(url, key)
                sb.table(table).upsert(chunk).execute()
                print(f"[supabase-client] wrote chunk {i}-{i+len(chunk)}")
                continue
            except Exception as e:
                print("[supabase-client] failed, falling back to REST:", e)
        if requests is None:
            raise RuntimeError("requests required for Supabase REST fallback")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE") or key
        rest_url = url.rstrip("/") + f"/rest/v1/{table}"
        headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}", "Content-Type": "application/json", "Prefer": "return=representation"}
        params = {"on_conflict": on_conflict, "upsert": "true"}
        r = requests.post(rest_url, params=params, headers=headers, data=json.dumps(chunk, default=str), timeout=60)
        if r.status_code not in (200,201):
            raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: {r.text}")
        print(f"[supabase-rest] wrote chunk {i}-{i+len(chunk)} status={r.status_code}")

# ---------------- main ----------------
def main():
    tickers = [t.strip() for t in os.environ.get("TICKERS", DEFAULT_TICKERS).split(",") if t.strip()]
    df = fetch_companies(tickers)
    use_rds = os.environ.get("USE_RDS", "0") == "1"

    if use_rds:
        conn = pg_connect()
        try:
            pg_upsert_companies(conn, df)
        finally:
            conn.close()
        return

    # supabase mode
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE") or os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("[main] SUPABASE not configured; printing sample")
        print(df.head(3).to_dict(orient="records"))
        return
    supabase_upsert(df, os.environ.get("SUPABASE_COMPANIES_TABLE", "companies"), supabase_url, supabase_key, on_conflict="ticker")

if __name__ == "__main__":
    main()
