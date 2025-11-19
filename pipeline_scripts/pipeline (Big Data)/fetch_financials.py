#!/usr/bin/env python3
# pipeline/fetch_financials.py
from __future__ import annotations

import os
import json
from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

# ---------- optional libs ----------
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
TABLE_NAME = os.environ.get("FINANCIALS_TABLE", "financials")
UNIQUE_CONSTRAINT = os.environ.get("FINANCIALS_UNIQUE_CONSTRAINT", "financials_unique")

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

def df_period_dict(df: Optional[pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
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
            cf  = tk.cashflow
        except Exception as e:
            print(f"[fetch_financials] {t} error: {e}")
            fin, bal, cf = None, None, None

        fin_map = df_period_dict(fin)
        bal_map = df_period_dict(bal)
        cf_map  = df_period_dict(cf)

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
            cf_r  = cf_map.get(p, {}) or {}

            def pnum(x, nd=2):
                return safe_decimal(x, ndigits=nd) if x is not None else None

            # prefer FY; if you later add quarterly, include period_type in unique key as needed
            period_dt = pd.to_datetime(p).date()

            rows.append({
                "ticker": t,
                "period_end": period_dt,  # date object (psycopg2 handles it cleanly)
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
                "free_cash_flow": None,  # derive if desired
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

# ---------- Postgres ----------
def pg_connect():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 required for RDS mode (pip install psycopg2-binary)")
    return psycopg2.connect(
        host=os.environ.get("PG_HOST"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DB"),
        user=os.environ.get("PG_USER"),
        password=os.environ.get("PG_PASS"),
        connect_timeout=10,
        sslmode=os.environ.get("PG_SSLMODE", "require"),
    )

def pg_ensure_unique_constraint(conn):
    """
    Ensure a unique constraint over (ticker, period_end) so ON CONFLICT has a valid target.
    Safe to run repeatedly.
    """
    sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.conname = '{UNIQUE_CONSTRAINT}'
              AND n.nspname = 'public'
        ) THEN
            ALTER TABLE public.{TABLE_NAME}
            ADD CONSTRAINT {UNIQUE_CONSTRAINT} UNIQUE (ticker, period_end);
        END IF;
    END$$;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"[pg] ensured UNIQUE constraint public.{TABLE_NAME}(ticker, period_end) as {UNIQUE_CONSTRAINT}")

def pg_upsert_financials(conn, df: pd.DataFrame):
    if df is None or df.empty:
        print("[pg] no financials to upsert")
        return

    cols = [
        "ticker","period_end","period_type","reported_currency","revenue","cost_of_revenue","gross_profit",
        "operating_income","net_income","eps_basic","eps_diluted","ebitda","gross_margin","operating_margin",
        "ebitda_margin","net_profit_margin","total_assets","total_liabilities","total_equity",
        "cash_and_equivalents","total_debt","operating_cashflow","capital_expenditures","free_cash_flow",
        "shares_outstanding","shares_float","market_cap","price_to_earnings","forward_pe","peg_ratio",
        "revenue_growth","earnings_growth","number_of_analysts","recommendation_mean","fetched_at","raw_json"
    ]

    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    # coerce integer-like columns to Python ints where possible
    for ic in INTEGER_COLS:
        if ic in df.columns:
            df[ic] = df[ic].apply(_coerce_int_for_df)

    # build tuples
    values = []
    for _, r in df.iterrows():
        row = []
        for c in cols:
            v = r[c]
            if pd.isna(v):
                row.append(None)
            elif isinstance(v, (dict, list)):
                row.append(pg_extras.Json(v))
            elif isinstance(v, Decimal):
                row.append(v)
            else:
                row.append(v)
        values.append(tuple(row))

    col_sql = ",".join(f'"{c}"' for c in cols)
    template = "(" + ",".join(["%s"] * len(cols)) + ")"

    # do not update the conflict keys
    dont_update = {"ticker", "period_end"}
    update_cols = [c for c in cols if c not in dont_update]
    set_sql = ",".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)

    sql = (
        f'INSERT INTO public.{TABLE_NAME} ({col_sql}) VALUES %s '
        f'ON CONFLICT ON CONSTRAINT {UNIQUE_CONSTRAINT} DO UPDATE SET {set_sql};'
    )

    with conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, values, template=template)
    conn.commit()
    print(f"[pg] upserted {len(values)} financial rows")

# ---------- coercion ----------
def _coerce_int_for_df(x):
    if pd.isna(x):
        return None
    if isinstance(x, int) and not isinstance(x, bool):
        return int(x)
    if isinstance(x, float):
        return int(x) if x.is_integer() else None
    if isinstance(x, Decimal):
        try:
            fv = float(x)
            return int(fv) if float(fv).is_integer() else None
        except Exception:
            return None
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        try:
            fv = float(s)
            return int(fv) if fv.is_integer() else None
        except Exception:
            return None
    try:
        import numpy as np
        if isinstance(x, (np.integer,)):
            return int(x)
    except Exception:
        pass
    try:
        return int(x)
    except Exception:
        return None

# ---------- Supabase upsert ----------
def supabase_upsert(df: pd.DataFrame, table: str, url: str, key: str, on_conflict: str = "ticker,period_end"):
    if df is None or df.empty:
        print("[supabase] no rows to upsert")
        return

    for ic in INTEGER_COLS:
        if ic in df.columns:
            df[ic] = df[ic].apply(_coerce_int_for_df)

    records = df.to_dict(orient="records")

    def norm(r):
        nr = {}
        for k, v in r.items():
            if pd.isna(v):
                nr[k] = None
            elif isinstance(v, (dict, list)):
                nr[k] = v
            elif isinstance(v, Decimal):
                try:
                    nr[k] = float(v)
                except Exception:
                    nr[k] = str(v)
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
                sb.table(table).upsert(chunk, on_conflict=on_conflict).execute()
                print(f"[supabase-client] upserted chunk {i}-{i+len(chunk)}")
                continue
            except Exception as e:
                print("[supabase-client] failed, falling back to REST:", e)

        if requests is None:
            raise RuntimeError("requests is required for Supabase REST fallback")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE") or key
        rest_url = url.rstrip("/") + f"/rest/v1/{table}"
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "resolution=merge-duplicates, return=representation",
            "Content-Type": "application/json",
        }
        params = {"on_conflict": on_conflict}
        r = requests.post(rest_url, params=params, headers=headers, data=json.dumps(chunk), timeout=60)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"[supabase-rest] failed {r.status_code}: {r.text}")
        print(f"[supabase-rest] upserted chunk {i}-{i+len(chunk)}")

# ---------- main ----------
def main():
    tickers = [t.strip() for t in os.environ.get("TICKERS", DEFAULT_TICKERS).split(",") if t.strip()]
    df = fetch_financials(tickers)

    use_rds = os.environ.get("USE_RDS", "0") == "1"
    if use_rds:
        conn = pg_connect()
        try:
            pg_ensure_unique_constraint(conn)  # make sure ON CONFLICT target exists
            pg_upsert_financials(conn, df)
        finally:
            conn.close()
        return

    # Supabase mode
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE") or os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("[main] SUPABASE not configured; sample rows:")
        print(df.head(5).to_dict(orient="records"))
        return
    supabase_upsert(df, os.environ.get("SUPABASE_FINANCIALS_TABLE", TABLE_NAME), supabase_url, supabase_key)

if __name__ == "__main__":
    main()
