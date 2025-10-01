#!/usr/bin/env python3
# pipeline/fetch_company_officers.py
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
DEFAULT_TICKERS = os.environ.get(
    "TICKERS",
    "AAPL,META,AMZN,NVDA,MSFT,NIO,XPEV,LI,ZK,PYPL,AXP,MA,GPN,V,FUTU,HOOD,TIGR,IBKR,GS,JPM,BLK,C,BX,KO,WMT,MCD,NKE,SBUX,COIN,BCS,AMD,BABA,PINS,BA,AVGO,JD,PDD,SNAP,FVRR,DJT,SHOP,SE"
)

TABLE_NAME = os.environ.get("OFFICERS_TABLE", "company_officers")
UNIQUE_CONSTRAINT = os.environ.get("OFFICERS_UNIQUE_CONSTRAINT", "company_officers_unique")
CONFLICT_COLUMNS = ("ticker", "name", "title", "fiscal_year")  # logical identity

INTEGER_COLS = {"year_of_birth", "age", "fiscal_year"}

# ---------- helpers ----------
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

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---------- fetch ----------
def fetch_officers(tickers: List[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
        except Exception as e:
            print(f"[fetch_officers] {t} error: {e}")
            info = {}
        officers = info.get("companyOfficers") or []
        for off in officers:
            extra_obj = {k: off.get(k) for k in off.keys()
                         if k not in ("name", "title", "yearBorn", "age", "fiscalYear", "totalPay")}
            total_pay = off.get("totalPay")
            rows.append({
                "ticker": t,
                "name": off.get("name"),
                "title": off.get("title"),
                "year_of_birth": to_int(off.get("yearBorn")),
                "age": to_int(off.get("age")),
                "fiscal_year": to_int(off.get("fiscalYear")),
                "total_pay": safe_decimal(total_pay, ndigits=2),
                "extra": extra_obj,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # ---- critical: coerce NULLs so ON CONFLICT will actually match ----
    # Use empty string for title and 0 for fiscal_year to collapse duplicates deterministically.
    if "title" in df.columns:
        df["title"] = df["title"].fillna("").astype(str)
    if "fiscal_year" in df.columns:
        # Coerce to integer, default 0 when missing
        df["fiscal_year"] = df["fiscal_year"].apply(lambda x: 0 if x is None or (isinstance(x, float) and pd.isna(x)) else int(x))

    # Clean integer columns (avoid 63.0)
    for ic in INTEGER_COLS:
        if ic in df.columns:
            df[ic] = df[ic].apply(_coerce_int_for_df)

    return df

def to_int(v) -> Optional[int]:
    if v in (None, "", float("nan")) or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        f = float(v)
        if f.is_integer():
            return int(f)
        return int(round(f))
    except Exception:
        try:
            return int(v)
        except Exception:
            return None

def _coerce_int_for_df(x):
    if pd.isna(x):
        return None
    if isinstance(x, bool):
        return int(x)
    try:
        f = float(x)
        return int(f) if float(f).is_integer() else int(round(f))
    except Exception:
        try:
            return int(x)
        except Exception:
            return None

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
    Ensure a unique constraint exists over (ticker,name,title,fiscal_year)
    so that ON CONFLICT has a valid target. Safe to run repeatedly.
    """
    cols = ", ".join(CONFLICT_COLUMNS)
    constraint = UNIQUE_CONSTRAINT
    table = TABLE_NAME

    sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.conname = '{constraint}'
              AND n.nspname = 'public'
        ) THEN
            ALTER TABLE public.{table}
            ADD CONSTRAINT {constraint} UNIQUE ({cols});
        END IF;
    END$$;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"[pg] ensured UNIQUE constraint public.{TABLE_NAME}({cols}) as {constraint}")

def pg_upsert_officers(conn, df: pd.DataFrame):
    if df is None or df.empty:
        print("[pg] no officers to upsert")
        return

    cols = ["ticker", "name", "title", "year_of_birth", "age", "fiscal_year",
            "total_pay", "extra", "created_at", "updated_at"]

    # add missing columns and order
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    # build value tuples with proper JSON handling
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

    # Preserve created_at, update others
    dont_update = set(CONFLICT_COLUMNS) | {"created_at"}
    update_cols = [c for c in cols if c not in dont_update]
    set_parts = []
    for c in update_cols:
        if c == "updated_at":
            set_parts.append(f'"updated_at" = EXCLUDED."updated_at"')
        elif c == "extra":
            set_parts.append(f'"extra" = EXCLUDED."extra"')
        else:
            set_parts.append(f'"{c}" = EXCLUDED."{c}"')
    # keep original created_at if present
    set_parts.append(f'"created_at" = COALESCE({TABLE_NAME}.created_at, EXCLUDED."created_at")')
    set_sql = ", ".join(set_parts)

    sql = (
        f'INSERT INTO public.{TABLE_NAME} ({col_sql}) VALUES %s '
        f'ON CONFLICT ON CONSTRAINT {UNIQUE_CONSTRAINT} '
        f'DO UPDATE SET {set_sql};'
    )

    with conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, values, template=template)
    conn.commit()
    print(f"[pg] upserted {len(values)} officers")

# ---------- Supabase ----------
def supabase_upsert(df: pd.DataFrame, table: str, url: str, key: str,
                    on_conflict: str = "ticker,name,title,fiscal_year"):
    if df is None or df.empty:
        print("[supabase] no rows to upsert")
        return

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

    records = [norm(r) for r in df.to_dict(orient="records")]
    chunk = 200
    for i in range(0, len(records), chunk):
        part = records[i:i+chunk]
        # client first
        if create_client is not None:
            try:
                sb = create_client(url, key)
                sb.table(table).upsert(part, on_conflict=on_conflict).execute()
                print(f"[supabase-client] upserted {i}-{i+len(part)}")
                continue
            except Exception as e:
                print("[supabase-client] failed, fallback to REST:", e)
        if requests is None:
            raise RuntimeError("requests required for Supabase REST fallback")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE") or key
        rest_url = url.rstrip("/") + f"/rest/v1/{table}"
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "resolution=merge-duplicates,return=representation",
            "Content-Type": "application/json",
        }
        params = {"on_conflict": on_conflict}
        r = requests.post(rest_url, params=params, headers=headers, data=json.dumps(part))
        if r.status_code not in (200, 201):
            raise RuntimeError(f"[supabase-rest] failed {r.status_code}: {r.text}")
        print(f"[supabase-rest] upserted {i}-{i+len(part)}")

# ---------- main ----------
def main():
    tickers = [t.strip() for t in os.environ.get("TICKERS", DEFAULT_TICKERS).split(",") if t.strip()]
    df = fetch_officers(tickers)

    if df is None or df.empty:
        print("[main] no officer rows fetched; exiting")
        return

    use_rds = os.environ.get("USE_RDS", "0") == "1"
    if use_rds:
        conn = pg_connect()
        try:
            pg_ensure_unique_constraint(conn)  # ensures ON CONFLICT target exists
            pg_upsert_officers(conn, df)
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
    supabase_upsert(df, os.environ.get("SUPABASE_OFFICERS_TABLE", TABLE_NAME), supabase_url, supabase_key)

if __name__ == "__main__":
    main()
