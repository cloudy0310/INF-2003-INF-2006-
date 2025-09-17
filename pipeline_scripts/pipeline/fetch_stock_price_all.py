"""
fetch_stock_price_all.py - DynamoDB/Supabase writer with strict AWS session + rich logs
"""
from __future__ import annotations
from dotenv import load_dotenv
import os, json
from decimal import Decimal
from typing import List, Optional
import pandas as pd
import numpy as np
import yfinance as yf

load_dotenv()  # loads .env from current working dir

# optional DB libs
try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception:
    boto3 = None

try:
    import requests
except Exception:
    requests = None

DEFAULT_TICKERS = os.environ.get(
    "TICKERS",
    "AAPL,META,AMZN,NVDA,MSFT,NIO,XPEV,LI,ZK,PYPL,AXP,MA,GPN,V,FUTU,HOOD,TIGR,IBKR,GS,JPM,BLK,C,BX,KO,WMT,MCD,NKE,SBUX,COIN,BCS,AMD,BABA,PINS,BA,AVGO,JD,PDD,SNAP,FVRR,DJT,SHOP,SE"
)

NUMERIC_COLS = [
    "open", "high", "low", "close",
    "bb_sma_20", "bb_upper_20", "bb_lower_20",
    "rsi_14", "macd", "macd_signal", "macd_hist"
]

# ---------- Indicators ----------
def calculate_indicators_full(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    delta = df["close"].diff(1)
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14, min_periods=1).mean()
    avg_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50.0)

    sma = df["close"].rolling(window=20, min_periods=1).mean()
    std_dev = df["close"].rolling(window=20, min_periods=1).std().fillna(0)
    upper = sma + 2 * std_dev
    lower = sma - 2 * std_dev

    df["macd"] = macd
    df["macd_signal"] = signal
    df["macd_hist"] = macd - signal
    df["rsi_14"] = rsi
    df["bb_sma_20"] = sma
    df["bb_upper_20"] = upper
    df["bb_lower_20"] = lower

    cond_buy = (
        (df["macd"] < df["macd_signal"]) &
        (df["macd"] < 0) &
        (df["rsi_14"] < 30) &
        (df["close"] <= df["bb_lower_20"])
    )
    cond_sell = (
        (df["macd"] > df["macd_signal"]) &
        (df["macd"] > 0) &
        (df["rsi_14"] > 70) &
        (df["close"] >= df["bb_upper_20"])
    )
    df["buy_signal"] = cond_buy.rolling(window=5, min_periods=1).sum() >= 1
    df["sell_signal"] = cond_sell.rolling(window=5, min_periods=1).sum() >= 1

    return df

# ---------- Supabase upsert ----------
def upsert_supabase(df: pd.DataFrame, table: str, url: str, key: str, on_conflict: str = "ticker,date") -> None:
    if df is None or df.empty:
        print("[upsert_supabase] dataframe empty, nothing to write")
        return

    records = df.to_dict(orient="records")

    def norm(r):
        nr = {}
        for k, v in r.items():
            if pd.isna(v):
                nr[k] = None
            elif isinstance(v, (np.integer,)):
                nr[k] = int(v)
            elif isinstance(v, (np.floating,)):
                nr[k] = float(round(float(v), 4))
            elif isinstance(v, (Decimal,)):
                nr[k] = float(round(float(v), 4))
            elif isinstance(v, (pd.Timestamp,)):
                nr[k] = v.strftime("%Y-%m-%d")
            else:
                nr[k] = v
        return nr

    normalized = [norm(r) for r in records]
    chunk_size = 200

    for i in range(0, len(normalized), chunk_size):
        chunk = normalized[i:i+chunk_size]
        if create_client is not None:
            try:
                supabase = create_client(url, key)
                resp = supabase.table(table).upsert(chunk).execute()
                status = getattr(resp, "status_code", None)
                data = getattr(resp, "data", None) or (resp.get("data") if isinstance(resp, dict) else None)
                error = getattr(resp, "error", None) or (resp.get("error") if isinstance(resp, dict) else None)
                print(f"[supabase-client] chunk {i}-{i+len(chunk)} status={status} data_len={len(data) if data is not None else 'unknown'} error={error}")
                if error:
                    raise RuntimeError(f"supabase client error: {error}")
                continue
            except Exception as e:
                print(f"[supabase-client] client upsert failed for chunk {i}-{i+len(chunk)}: {e}. Falling back to REST...")

        if requests is None:
            raise RuntimeError("requests not installed; cannot perform REST fallback")

        service_key = os.environ.get("SUPABASE_SERVICE_ROLE") or key
        rest_url = url.rstrip("/") + f"/rest/v1/{table}"
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        params = {"on_conflict": on_conflict, "upsert": "true"}

        r = requests.post(rest_url, params=params, headers=headers, data=json.dumps(chunk), timeout=60)
        text_preview = (r.text[:400] + "...") if r.text and len(r.text) > 400 else r.text
        print(f"[rest] chunk {i}-{i+len(chunk)} status={r.status_code} text={text_preview}")
        if r.status_code not in (200, 201):
            raise RuntimeError(f"REST upsert failed: {r.status_code} {r.text}")

# ---------- DynamoDB upsert (FORCED profile/region + logs) ----------
def upsert_dynamodb(df: pd.DataFrame, table_name: str, region: Optional[str] = None) -> None:
    if boto3 is None:
        raise RuntimeError("boto3 not installed")

    # Force the exact same signing context your CLI uses
    region  = (region or os.getenv("AWS_REGION", "ap-southeast-1")).strip()
    profile = os.getenv("AWS_PROFILE", "default").strip()

    session = boto3.Session(profile_name=profile, region_name=region)

    # Log identity + endpoint so we can see exactly what’s used
    sts = session.client("sts")
    who = sts.get_caller_identity()
    ddb_client = session.client("dynamodb")
    print("[dynamodb] profile =", session.profile_name)
    print("[dynamodb] region  =", session.region_name)
    print("[dynamodb] endpoint=", ddb_client.meta.endpoint_url)
    print("[dynamodb] caller  =", who)

    ddb = session.resource("dynamodb")
    table = ddb.Table(table_name.strip())

    records = df.to_dict(orient="records")
    print(f"[dynamodb] preparing to write {len(records)} records")
    if records:
        print("[dynamodb] sample raw record:", records[:1])

    # Convert + enforce keys
    prepared = []
    for r in records:
        item = {}
        for k, v in r.items():
            if pd.isna(v):
                continue
            if k in NUMERIC_COLS + ["open","high","low","close"]:
                item[k] = Decimal(str(round(float(v), 4)))
            elif k == "volume":
                item[k] = int(v)
            elif k in ("buy_signal", "sell_signal"):
                item[k] = bool(v)
            else:
                item[k] = str(v)

        if "ticker" not in item or "date" not in item:
            print("⚠️  Skipping row missing ticker/date:", item)
            continue
        prepared.append(item)

    if not prepared:
        print("[dynamodb] nothing to write after preparation")
        return

    print("[dynamodb] sample prepared item:", prepared[0])

    # Write with batch_writer (handles retries automatically)
    try:
        wrote = 0
        with table.batch_writer() as batch:
            for i, it in enumerate(prepared, 1):
                batch.put_item(Item=it)
                if i % 5000 == 0:
                    print(f"[dynamodb] wrote {i} items...")
                wrote = i
        print(f"[dynamodb] wrote {wrote} items total")
    except ClientError as e:
        print("[dynamodb] batch write failed; example item:", prepared[0])
        raise

# ---------- Fetch + prepare ----------
def fetch_all_and_upsert(tickers: List[str], start: Optional[str] = None) -> pd.DataFrame:
    frames = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        print(f"[backfill] fetching {t} start={start or 'period=max'}")
        try:
            tk = yf.Ticker(t)
            if start:
                hist = tk.history(start=start, auto_adjust=False)
            else:
                hist = tk.history(period="max", auto_adjust=False)
            if hist is None or hist.empty:
                print(f"[backfill] no history for {t}")
                continue
            df = hist.reset_index().rename(columns={
                "Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
            })
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"[backfill] failed {t}: {e}")
            continue

        df = calculate_indicators_full(df)
        df["ticker"] = t

        cols = [
            "ticker", "date", "open", "high", "low", "close", "volume",
            "bb_sma_20", "bb_upper_20", "bb_lower_20", "rsi_14",
            "macd", "macd_signal", "macd_hist", "buy_signal", "sell_signal"
        ]
        for c in cols:
            if c not in df.columns:
                df[c] = pd.NA
        out = df[cols].copy()

        for c in ["open", "high", "low", "close"] + [c for c in NUMERIC_COLS if c in out.columns]:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(4)
        out["volume"] = out["volume"].fillna(0).astype("int64")
        out["buy_signal"] = out["buy_signal"].astype(bool)
        out["sell_signal"] = out["sell_signal"].astype(bool)

        frames.append(out)

    if not frames:
        return pd.DataFrame(columns=[
            "ticker","date","open","high","low","close","volume",
            "bb_sma_20","bb_upper_20","bb_lower_20","rsi_14",
            "macd","macd_signal","macd_hist","buy_signal","sell_signal"
        ])
    return pd.concat(frames, ignore_index=True)

# ---------- Main ----------
if __name__ == "__main__":
    tickers = [t.strip() for t in os.environ.get("TICKERS", DEFAULT_TICKERS).split(",") if t.strip()]
    start = os.environ.get("START_DATE")
    df = fetch_all_and_upsert(tickers, start=start)

    print("[main] total rows prepared:", len(df))
    if not df.empty:
        print("[main] sample row:", df.head(1).to_dict(orient="records"))

    use_ddb = os.environ.get("USE_DYNAMODB", "0") == "1"
    if use_ddb:
        ddb_table = os.environ.get("DDB_TABLE", "stock_prices")
        region = os.environ.get("AWS_REGION", "ap-southeast-1")
        if not ddb_table:
            print("[main] DDB_TABLE not set — not writing")
        else:
            # optional: strip proxies if your network injects headers
            for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
                os.environ.pop(k, None)
            upsert_dynamodb(df, ddb_table, region=region)
    else:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE") or os.environ.get("SUPABASE_KEY")
        supabase_table = os.environ.get("SUPABASE_TABLE", "stock_prices")
        if supabase_url and supabase_key:
            upsert_supabase(df, supabase_table, supabase_url, supabase_key)
        else:
            print("[main] SUPABASE_URL or SUPABASE_KEY not set; printing sample rows instead")
            print(df.head().to_dict(orient="records"))
