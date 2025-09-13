#!/usr/bin/env python3
# etl/fetch_financials.py
from __future__ import annotations
import os
import json
from decimal import Decimal
from typing import List, Optional
from datetime import datetime, timezone
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

# ---------- config ----------
DEFAULT_TICKERS = os.environ.get("TICKERS", "AAPL,MSFT")

# integer-like columns for financials table
INTEGER_COLS = {"shares_outstanding", "shares_float", "number_of_analysts"}

# ---------- helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def safe_decimal(x, ndigits: int = 2) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        quant = Decimal("1." + "0" * ndigits)
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
            if chunk:
                yield chunk
            break
        yield chunk

def df_period_dict(df):
    out = {}
    if df is None or df.empty:
        return out
    for col in df.columns:
        try:
            key = pd.to_datetime(col).date().isoformat()
        except Exception:
            key = str(col)
        s = df[col].to_dict()
        s = {k: (None if pd.isna(v) else v) for k, v in s.items()}
        out[key] = s
    return out

# ---------- fetch ----------
def fetch_financials(tickers: List[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        try:
            tk = yf.Ticker(t)
            fin = tk.financials
            bal = tk.balance_sheet
            cf = tk.cashflow
        except Exception as e:
            print(f"[fetch_financials] {t} error: {e}")
            fin, bal, cf = None, None, None

        fin_map = df_period_dict(fin)
        bal_map = df_period_dict(bal)
        cf_map = df_period_dict(cf)

        all_periods = sorted(set(list(fin_map.keys()) + list(bal_map.keys()) + list(cf_map.keys())))
        if not all_periods:
            info = getattr(tk, "info", {}) or {}
            mrq = info.get("mostRecentQuarter")
            if mrq:
                try:
                    all_periods = [pd.to_datetime(mrq).date().isoformat()]
                except Exception:
                    pass

        for p in all_periods:
            fin_r = fin_map.get(p, {}) or {}
            bal_r = bal_map.get(p, {}) or {}
            cf_r = cf_map.get(p, {}) or {}

            def pnum(x, nd=2):
                return safe_decimal(x, ndigits=nd) if x is not None else None

            rows.append({
                "ticker": t,
                "period_end": pd.to_datetime(p).date().isoformat(),
                "period_type": "FY",
                "reported_currency": None,
                "revenue": pnum(fin_r.get("Total Revenue")) or pnum(fin_r.get("Revenue")),
                "cost_of_revenue": pnum(fin_r.get("Cost of Revenue")) or pnum(fin_r.get("CostOfRevenue")),
                "gross_profit": pnum(fin_r.get("Gross Profit")) or pnum(fin_r.get("GrossProfit")),
                "operating_income": pnum(fin_r.get("Operating Income")) or pnum(fin_r.get("OperatingIncome")),
                "net_income": pnum(fin_r.get("Net Income")) or pnum(fin_r.get("NetIncome")),
                "eps_basic": pnum(fin_r.get("Basic EPS"), nd=6),
                "eps_diluted": pnum(fin_r.get("Diluted EPS"), nd=6),
                "ebitda": pnum(fin_r.get("EBITDA")),
                "gross_margin": pnum(fin_r.get("Gross Margin"), nd=8),
                "operating_margin": pnum(fin_r.get("Operating Margin"), nd=8),
                "ebitda_margin": pnum(fin_r.get("EBITDA Margin"), nd=8),
                "net_profit_margin": pnum(fin_r.get("Net Profit Margin"), nd=8),
                "total_assets": pnum(bal_r.get("Total Assets")),
                "total_liabilities": pnum(bal_r.get("Total Liab")) or pnum(bal_r.get("totalLiabilities")),
                "total_equity": pnum(bal_r.get("Total Stockholder's Equity")) or pnum(bal_r.get("Total stockholder equity")),
                "cash_and_equivalents": pnum(bal_r.get("Cash And Cash Equivalents")) or pnum(bal_r.get("cashAndShortTermInvestments")),
                "total_debt": pnum(bal_r.get("Total Debt")),
                "operating_cashflow": pnum(cf_r.get("Total Cash From Operating Activities")),
                "capital_expenditures": pnum(cf_r.get("Capital Expenditures")),
                "free_cash_flow": None,
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
                "fetched_at": now_iso(),
                "raw_json": {"income": fin_r, "balance": bal_r, "cashflow": cf_r}
            })
    return pd.DataFrame(rows)

# ---------- Postgres helpers ----------
def pg_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 required for RDS mode (pip install psycopg2-binary)")
    return psycopg2.connect(
        host=os.environ.get("PG_HOST"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB"),
        user=os.environ.get("PG_USER"),
        password=os.environ.get("PG_PASS"),
        connect_timeout=10
    )

def pg_create_unique_index_if_needed(conn):
    sql = "CREATE UNIQUE INDEX IF NOT EXISTS idx_financials_unique ON financials (ticker, period_end);"
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("[pg] ensured unique index for financials")

def pg_upsert_financials(conn, df: pd.DataFrame):
    if df is None or df.empty:
        print("[pg] no financials to upsert")
        return
    cols = [
        "ticker","period_end","period_type","reported_currency","revenue","cost_of_revenue","gross_profit","operating_income","net_income",
        "eps_basic","eps_diluted","ebitda","gross_margin","operating_margin","ebitda_margin","net_profit_margin","total_assets",
        "total_liabilities","total_equity","cash_and_equivalents","total_debt","operating_cashflow","capital_expenditures","free_cash_flow",
        "shares_outstanding","shares_float","market_cap","price_to_earnings","forward_pe","peg_ratio","revenue_growth","earnings_growth",
        "number_of_analysts","recommendation_mean","fetched_at","raw_json"
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    # coerce integer-like columns to Python ints where possible to avoid Postgres errors
    for ic in INTEGER_COLS:
        if ic in df.columns:
            df[ic] = df[ic].apply(_coerce_int_for_df)

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

    col_sql = ",".join(f'"{c}"' for c in cols)
    template = "(" + ",".join(["%s"] * len(cols)) + ")"
    update_cols = [c for c in cols if c not in ("ticker","period_end")]
    if update_cols:
        set_sql = ",".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
        on_conflict_sql = f"ON CONFLICT (ticker, period_end) DO UPDATE SET {set_sql}"
    else:
        on_conflict_sql = "ON CONFLICT DO NOTHING"
    sql = f'INSERT INTO financials ({col_sql}) VALUES %s {on_conflict_sql};'

    with conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, values, template=template)
    conn.commit()
    print(f"[pg] upserted {len(values)} financial rows")

# ---------- coercion helper ----------
def _coerce_int_for_df(x):
    """Coerce DataFrame cell to Python int if integer-valued, otherwise return None or original"""
    if pd.isna(x):
        return None
    # already int
    if isinstance(x, int) and not isinstance(x, bool):
        return int(x)
    # float that's integer-like
    if isinstance(x, float):
        return int(x) if x.is_integer() else None
    # Decimal integer-like
    if isinstance(x, Decimal):
        try:
            fv = float(x)
            return int(fv) if float(fv).is_integer() else None
        except Exception:
            return None
    # string like "63" or "63.0"
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        try:
            fv = float(s)
            return int(fv) if fv.is_integer() else None
        except Exception:
            return None
    # numpy integer types
    try:
        import numpy as np
        if isinstance(x, (np.integer,)):
            return int(x)
    except Exception:
        pass
    # fallback: try int conversion
    try:
        return int(x)
    except Exception:
        return None

# ---------- Supabase upsert (client + REST fallback) ----------
def supabase_upsert(df: pd.DataFrame, table: str, url: str, key: str, on_conflict: str = "ticker,period_end"):
    """
    Upsert df into Supabase (PostgREST) with coercion for integer columns.
    """
    if df is None or df.empty:
        print("[supabase] no rows to upsert")
        return

    # coerce integer-like columns first
    for ic in INTEGER_COLS:
        if ic in df.columns:
            df[ic] = df[ic].apply(_coerce_int_for_df)

    records = df.to_dict(orient="records")

    def norm(r):
        nr = {}
        for k, v in r.items():
            if pd.isna(v):
                nr[k] = None
                continue
            if isinstance(v, (dict, list)):
                nr[k] = v
                continue
            if isinstance(v, Decimal):
                # convert Decimal -> float for JSON payloads (Supabase)
                try:
                    nr[k] = float(v)
                except Exception:
                    nr[k] = str(v)
                continue
            # numeric strings -> parse
            if isinstance(v, str):
                s = v.strip()
                if s == "":
                    nr[k] = None
                    continue
                try:
                    if s.lstrip("-").isdigit():
                        nr[k] = int(s)
                        continue
                    fv = float(s)
                    nr[k] = fv
                    continue
                except Exception:
                    nr[k] = v
                    continue
            # leave ints/floats/bools as-is
            nr[k] = v
        return nr

    payloads = [norm(r) for r in records]
    chunk_size = 200

    for i in range(0, len(payloads), chunk_size):
        chunk = payloads[i:i+chunk_size]

        # debug sample
        print(f"[supabase] sample payload (first 3) for chunk {i}-{i+len(chunk)}:")
        for s in chunk[:3]:
            print(s)

        # try supabase client upsert first, passing on_conflict
        if create_client is not None:
            try:
                sb = create_client(url, key)
                sb.table(table).upsert(chunk, on_conflict=on_conflict).execute()
                print(f"[supabase-client] upserted chunk {i}-{i+len(chunk)}")
                continue
            except Exception as e:
                msg = getattr(e, "args", [str(e)])[0]
                print("[supabase-client] client failed, falling back to REST:", msg)

        # REST fallback
        if requests is None:
            raise RuntimeError("requests is required for Supabase REST fallback")

        service_key = os.environ.get("SUPABASE_SERVICE_ROLE") or key
        rest_url = url.rstrip("/") + f"/rest/v1/{table}"
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "resolution=merge-duplicates, return=representation"
        }
        params = {"on_conflict": on_conflict}

        r = requests.post(rest_url, params=params, headers=headers, json=chunk, timeout=60)
        text_preview = (r.text[:400] + "...") if r.text and len(r.text) > 400 else r.text
        print(f"[supabase-rest] chunk {i}-{i+len(chunk)} status={r.status_code} text={text_preview}")

        if r.status_code not in (200, 201):
            if r.status_code == 400 and "invalid input syntax for type integer" in (r.text or ""):
                print("[supabase] server rejected payload due to integer parse error. Sample payload (first 10):")
                for sample in chunk[:10]:
                    print(sample)
                raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: {r.text}")
            if r.status_code == 400 and "no unique or exclusion constraint" in (r.text or ""):
                raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: missing unique index for on_conflict={on_conflict}. DB error: {r.text}")
            raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: {r.text}")

# ---------- main ----------
def main():
    tickers = [t.strip() for t in os.environ.get("TICKERS", DEFAULT_TICKERS).split(",") if t.strip()]
    df = fetch_financials(tickers)
    use_rds = os.environ.get("USE_RDS", "0") == "1"
    if use_rds:
        conn = pg_connect()
        try:
            if os.environ.get("CREATE_INDEXES", "0") == "1":
                pg_create_unique_index_if_needed(conn)
            pg_upsert_financials(conn, df)
        finally:
            conn.close()
        return

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE") or os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("[main] SUPABASE not configured; printing sample")
        print(df.head(5).to_dict(orient="records"))
        return
    supabase_upsert(df, os.environ.get("SUPABASE_FINANCIALS_TABLE", "financials"), supabase_url, supabase_key)

if __name__ == "__main__":
    main()
