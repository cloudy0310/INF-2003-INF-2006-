# fetch_company_officers.py
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
DEFAULT_TICKERS = os.environ.get(
    "TICKERS",
    "AAPL,META,AMZN,NVDA,MSFT,NIO,XPEV,LI,ZK,PYPL,AXP,MA,GPN,V,FUTU,HOOD,TIGR,IBKR,GS,JPM,BLK,C,BX,KO,WMT,MCD,NKE,SBUX,COIN,BCS,AMD,BABA,PINS,BA,AVGO,JD,PDD,SNAP,FVRR,DJT,SHOP,SE"
)

# integer columns in DB
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
            extra_obj = {k: off.get(k) for k in off.keys() if k not in ("name", "title", "yearBorn", "age", "fiscalYear", "totalPay")}
            total_pay = off.get("totalPay")
            rows.append({
                "ticker": t,
                "name": off.get("name"),
                "title": off.get("title"),
                "year_of_birth": int(off.get("yearBorn")) if off.get("yearBorn") not in (None, float("nan")) else None,
                "age": int(off.get("age")) if off.get("age") not in (None, float("nan")) else None,
                "fiscal_year": int(off.get("fiscalYear")) if off.get("fiscalYear") not in (None, float("nan")) else None,
                "total_pay": safe_decimal(total_pay, ndigits=2),
                "extra": extra_obj,
                "created_at": now_iso(),
                "updated_at": now_iso()
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
    sql = "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_officers_unique ON company_officers (ticker, name, title, fiscal_year);"
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("[pg] ensured unique index for company_officers")

def pg_upsert_officers(conn, df: pd.DataFrame):
    if df is None or df.empty:
        print("[pg] no officers to upsert")
        return

    cols = ["ticker", "name", "title", "year_of_birth", "age", "fiscal_year", "total_pay", "extra", "created_at", "updated_at"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    # ensure integer columns are ints where possible (avoid sending floats like 63.0)
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

    # Build SET clause: preserve created_at on conflict, update others (including updated_at)
    update_cols = [c for c in cols if c not in ("ticker", "name", "title", "fiscal_year")]
    set_parts = []
    for c in update_cols:
        if c == "created_at":
            # preserve existing created_at if present
            set_parts.append(f'"created_at" = COALESCE(company_officers.created_at, EXCLUDED."created_at")')
        else:
            set_parts.append(f'"{c}" = EXCLUDED."{c}"')
    set_sql = ",".join(set_parts)

    on_conflict_sql = f'ON CONFLICT (ticker, name, title, fiscal_year) DO UPDATE SET {set_sql}'

    sql = f'INSERT INTO company_officers ({col_sql}) VALUES %s {on_conflict_sql};'

    with conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, values, template=template)
    conn.commit()
    print(f"[pg] upserted {len(values)} officers")

# ---------- coercion helpers ----------
def _coerce_int_for_df(x):
    """Coerce a single DataFrame cell to int if it represents an integer; else leave as-is."""
    if pd.isna(x):
        return None
    # int already
    if isinstance(x, int) and not isinstance(x, bool):
        return int(x)
    # float that's integer-like
    if isinstance(x, float):
        return int(x) if x.is_integer() else x
    # Decimal integer-like
    if isinstance(x, Decimal):
        try:
            fv = float(x)
            return int(fv) if float(fv).is_integer() else x
        except Exception:
            return x
    # string like "63" or "63.0"
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        try:
            fv = float(s)
            return int(fv) if fv.is_integer() else x
        except Exception:
            return x
    # fallback: try int conversion
    try:
        return int(x)
    except Exception:
        return x

# ---------- Supabase upsert (client + REST fallback) ----------
def supabase_upsert(df: pd.DataFrame, table: str, url: str, key: str,
                    on_conflict: str = "ticker,name,title,fiscal_year"):
    """
    Defensive Supabase upsert:
     - strongly coerce integer columns to Python int (or None)
     - print a small sample payload before POST
     - fallback to REST if supabase client fails
    """
    import numpy as np

    if df is None or df.empty:
        print("[supabase] no rows to upsert")
        return

    # Ensure integer columns become Python ints (not numpy ints/floats or strings)
    def coerce_to_int_py(v):
        # None/NA
        if pd.isna(v):
            return None
        # direct ints
        if isinstance(v, int) and not isinstance(v, bool):
            return int(v)
        # numpy integer types
        if isinstance(v, (np.integer,)):
            return int(v)
        # Decimal
        if isinstance(v, Decimal):
            try:
                fv = float(v)
                if float(fv).is_integer():
                    return int(fv)
                return None
            except Exception:
                return None
        # floats (numpy.float64 or float)
        if isinstance(v, (float, np.floating)):
            return int(v) if float(v).is_integer() else None
        # strings: try parse "63", "63.0"
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return None
            # allow integer-like strings and "63.0"
            try:
                if s.lstrip("-").isdigit():
                    return int(s)
                fv = float(s)
                if fv.is_integer():
                    return int(fv)
                return None
            except Exception:
                return None
        # fallback: try float -> int
        try:
            fv = float(v)
            return int(fv) if float(fv).is_integer() else None
        except Exception:
            return None

    # apply coercion in-place for safety (so we do not carry e.g. "63.0" strings)
    for ic in INTEGER_COLS:
        if ic in df.columns:
            df[ic] = df[ic].apply(coerce_to_int_py)

    # Build payload records with robust typing
    records = df.to_dict(orient="records")

    def norm(r):
        nr = {}
        for k, v in r.items():
            # pandas NA
            if pd.isna(v):
                nr[k] = None
                continue
            # JSON fields untouched
            if isinstance(v, (dict, list)):
                nr[k] = v
                continue
            # integer columns should already be Python int or None
            if k in INTEGER_COLS:
                # final check: if not int, log and set None (so DB won't get a string)
                if isinstance(v, (int,)) and not isinstance(v, bool):
                    nr[k] = int(v)
                else:
                    # convert numpy ints too
                    try:
                        nr[k] = int(v)
                    except Exception:
                        nr[k] = None
                continue
            # Decimal -> float
            if isinstance(v, Decimal):
                try:
                    nr[k] = float(v)
                except Exception:
                    nr[k] = str(v)
                continue
            # numpy scalar -> python native
            if isinstance(v, (np.integer, np.floating)):
                nr[k] = (int(v) if isinstance(v, np.integer) else float(v))
                continue
            # string numeric -> try parse to number
            if isinstance(v, str):
                s = v.strip()
                if s == "":
                    nr[k] = None
                    continue
                try:
                    if s.lstrip("-").isdigit():
                        nr[k] = int(s); continue
                    fv = float(s)
                    nr[k] = fv; continue
                except Exception:
                    nr[k] = v
                    continue
            # fallback keep as-is (bool, int, float)
            nr[k] = v
        return nr

    payloads = [norm(r) for r in records]
    chunk_size = 200

    # Debug helper: show rows where integer columns are still non-int (string/float)
    def debug_find_bad_integer_rows(payload_chunk):
        bad = []
        for rec in payload_chunk:
            for ic in INTEGER_COLS:
                if ic in rec:
                    val = rec[ic]
                    # treat numeric floats non-integer as bad, and strings as bad
                    if isinstance(val, str):
                        bad.append((rec.get("ticker"), ic, val))
                    elif isinstance(val, float) and not float(val).is_integer():
                        bad.append((rec.get("ticker"), ic, val))
        return bad

    for i in range(0, len(payloads), chunk_size):
        chunk = payloads[i:i+chunk_size]

        # print small sample for debugging so you can inspect before server rejects
        print(f"[supabase] sample payload (first 3) for chunk {i}-{i+len(chunk)}:")
        for s in chunk[:3]:
            print(s)

        bads = debug_find_bad_integer_rows(chunk)
        if bads:
            print("[supabase][warning] detected problematic integer values in payload (ticker, col, value):")
            for b in bads[:10]:
                print(" ", b)
            # continue and let server reject if still wrong; but this log helps debug

        # try supabase client upsert first (with on_conflict)
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
            # If it's an integer parse error, print sample payload to help debug
            if r.status_code == 400 and "invalid input syntax for type integer" in (r.text or ""):
                print("[supabase] server rejected payload due to integer parse error. Sample payload (first 20):")
                for sample in chunk[:20]:
                    print(sample)
                raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: {r.text}")
            if r.status_code == 400 and "no unique or exclusion constraint" in (r.text or ""):
                raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: missing unique index for on_conflict={on_conflict}. DB error: {r.text}")
            raise RuntimeError(f"Supabase REST upsert failed {r.status_code}: {r.text}")


# ---------- main ----------
def main():
    tickers = [t.strip() for t in os.environ.get("TICKERS", DEFAULT_TICKERS).split(",") if t.strip()]
    df = fetch_officers(tickers)

    # quick safety: if df empty, exit
    if df is None or df.empty:
        print("[main] no officer rows fetched; exiting")
        return

    # RDS mode
    use_rds = os.environ.get("USE_RDS", "0") == "1"
    if use_rds:
        conn = pg_connect()
        try:
            if os.environ.get("CREATE_INDEXES", "0") == "1":
                pg_create_unique_index_if_needed(conn)
            # pg_upsert will coerce ints inside
            pg_upsert_officers(conn, df)
        finally:
            conn.close()
        return

    # Supabase mode (default)
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE") or os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("[main] SUPABASE not configured; printing sample rows")
        print(df.head(5).to_dict(orient="records"))
        return

    supabase_upsert(df, os.environ.get("SUPABASE_OFFICERS_TABLE", "company_officers"), supabase_url, supabase_key)

if __name__ == "__main__":
    main()
