"""
Updated from fetch_stock_price_all.py to support a daily scheduled job that:
 - fetches sufficient historical data for each ticker (lookback window)
 - computes indicators (MACD, RSI, Bollinger) on the history
 - extracts exactly the *previous trading day's* row per ticker (handles weekends/holidays)
 - upserts only that single row per ticker to Supabase or DynamoDB

Features:
 - env / CLI controls: DAILY_UPDATE (or --daily), LOOKBACK_DAYS, TICKERS, USE_DYNAMODB
 - safer chunking & numeric normalization
 - helpful logging for missing rows

Requirements: pandas, numpy, yfinance, python-dotenv, requests (for REST fallback)
Optional: supabase (supabase-py), boto3

Scheduling suggestions (examples shown in README below): cron, systemd timer, AWS EventBridge -> Lambda (packaged), or GitHub Actions.
"""
from __future__ import annotations
from dotenv import load_dotenv
from pathlib import Path
import os
import json
from decimal import Decimal
from typing import List, Optional
import argparse
import pandas as pd
import numpy as np
import yfinance as yf
import datetime

load_dotenv()

# optional DB libs
try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    import boto3
except Exception:
    boto3 = None

# requests for REST fallback
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

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    # RSI(14)
    delta = df["close"].diff(1)
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14, min_periods=1).mean()
    avg_loss = loss.rolling(window=14, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50.0)

    # Bollinger Bands
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

# ---------- Helper utilities ----------
def chunked(iterable, size=500):
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

# ---------- Robust Supabase upsert (client + REST fallback) ----------
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
            print("[rest] requests not installed; cannot perform REST fallback. Install 'requests' or 'supabase' package.")
            raise RuntimeError("Neither supabase client succeeded nor requests available for REST fallback")

        service_key = os.environ.get("SUPABASE_SERVICE_ROLE") or key
        rest_url = url.rstrip("/") + f"/rest/v1/{table}"
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        params = {
            "on_conflict": on_conflict,
            "upsert": "true"
        }

        try:
            r = requests.post(rest_url, params=params, headers=headers, data=json.dumps(chunk), timeout=60)
            text_preview = (r.text[:400] + "...") if r.text and len(r.text) > 400 else r.text
            print(f"[rest] chunk {i}-{i+len(chunk)} status={r.status_code} text={text_preview}")
            if r.status_code not in (200, 201):
                raise RuntimeError(f"REST upsert failed: {r.status_code} {r.text}")
        except Exception as e:
            print(f"[rest] upsert exception for chunk {i}-{i+len(chunk)}: {e}")
            raise

# ---------- DynamoDB upsert (unchanged) ----------
def upsert_dynamodb(df: pd.DataFrame, table_name: str, region: Optional[str] = None) -> None:
    if boto3 is None:
        raise RuntimeError("boto3 not installed")
    session = boto3.session.Session()
    ddb = session.resource("dynamodb", region_name=region) if region else session.resource("dynamodb")
    table = ddb.Table(table_name)

    records = df.to_dict(orient="records")
    for i in range(0, len(records), 25):
        chunk = records[i:i+25]
        with table.batch_writer() as batch:
            for r in chunk:
                item = {}
                for k, v in r.items():
                    if pd.isna(v):
                        continue
                    if k in NUMERIC_COLS + ["open", "high", "low", "close"]:
                        item[k] = Decimal(str(round(float(v), 4)))
                    elif k == "volume":
                        item[k] = int(v)
                    elif k in ("buy_signal", "sell_signal"):
                        item[k] = bool(v)
                    else:
                        item[k] = str(v)
                batch.put_item(Item=item)
        print(f"[dynamodb] wrote {len(chunk)} items")

# ---------- Fetch previous trading day and compose single-row dataframe ----------
def fetch_previous_trading_rows(tickers: List[str], lookback_days: int = 180) -> pd.DataFrame:
    """
    For each ticker:
      - fetch `lookback_days` of history (sufficient to compute indicators)
      - compute indicators on the whole history
      - determine the previous trading day relative to `today` and extract that row
    Returns concatenated DataFrame with one row per ticker (for prev trading day)
    """
    frames = []
    today = datetime.date.today()

    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        print(f"[daily] fetching {t} lookback_days={lookback_days}")
        try:
            tk = yf.Ticker(t)
            hist = tk.history(period=f"{lookback_days}d", auto_adjust=False)
            if hist is None or hist.empty:
                print(f"[daily] no history for {t}")
                continue
            df = hist.reset_index().rename(columns={
                "Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
            })
            # normalize date column (no tz)
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

            # find previous trading date: if last available date == today -> pick penultimate
            last_date = df["date"].dt.date.iloc[-1]
            if last_date == today:
                if len(df) < 2:
                    print(f"[daily] only today's partial data for {t}; skipping")
                    continue
                target_date = df["date"].dt.date.iloc[-2]
            else:
                target_date = last_date

            # compute indicators on full df
            df_ind = df.copy()
            # ensure 'close' numeric
            df_ind["close"] = pd.to_numeric(df_ind["close"], errors="coerce")
            full = calculate_indicators_full(df_ind.assign(date=df_ind["date"].dt.strftime("%Y-%m-%d")))
            full["date"] = pd.to_datetime(full["date"]).dt.tz_localize(None)

            # find row for target_date
            row = full[full["date"].dt.date == target_date]
            if row.empty:
                print(f"[daily] no row for {t} on {target_date}; available last_date={last_date}")
                continue

            row = row.copy()
            row["ticker"] = t
            # format date as ISO date string
            row["date"] = row["date"].dt.strftime("%Y-%m-%d")

            cols = [
                "ticker", "date", "open", "high", "low", "close", "volume",
                "bb_sma_20", "bb_upper_20", "bb_lower_20", "rsi_14",
                "macd", "macd_signal", "macd_hist", "buy_signal", "sell_signal"
            ]
            for c in cols:
                if c not in row.columns:
                    row[c] = pd.NA

            out = row[cols].copy()

            for c in ["open", "high", "low", "close"] + [c for c in NUMERIC_COLS if c in out.columns]:
                out[c] = pd.to_numeric(out[c], errors="coerce").round(4)
            out["volume"] = out["volume"].fillna(0).astype("int64")
            out["buy_signal"] = out["buy_signal"].astype(bool)
            out["sell_signal"] = out["sell_signal"].astype(bool)

            frames.append(out)
        except Exception as e:
            print(f"[daily] failed {t}: {e}")
            continue

    if not frames:
        return pd.DataFrame(columns=[
            "ticker","date","open","high","low","close","volume",
            "bb_sma_20","bb_upper_20","bb_lower_20","rsi_14",
            "macd","macd_signal","macd_hist","buy_signal","sell_signal"
        ])
    return pd.concat(frames, ignore_index=True)

# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="Fetch previous trading day's prices and upsert indicators")
    parser.add_argument("--daily", action="store_true", help="Run daily update (only previous trading day's rows)")
    parser.add_argument("--lookback", type=int, default=int(os.environ.get("LOOKBACK_DAYS", "180")), help="Lookback days for indicator calculation")
    parser.add_argument("--tickers", type=str, default=os.environ.get("TICKERS", DEFAULT_TICKERS), help="Comma-separated tickers to fetch")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]

    if args.daily:
        df = fetch_previous_trading_rows(tickers, lookback_days=args.lookback)
    else:
        # fall back to full backfill like original script if not daily
        # reuse previous function fetch_all_and_upsert behavior: fetch full history per ticker
        # For simplicity we call fetch_previous_trading_rows with large lookback and then expand to full history
        # but here we'll just fetch lookback and upsert everything available in that window.
        print("[main] non-daily mode: fetching lookback window for each ticker and upserting all fetched rows")
        # naive behavior: fetch lookback and upsert all rows in that window (use existing fetch_all_and_upsert logic if desired)
        frames = []
        for t in tickers:
            try:
                tk = yf.Ticker(t)
                hist = tk.history(period=f"{args.lookback}d", auto_adjust=False)
                if hist is None or hist.empty:
                    continue
                df_hist = hist.reset_index().rename(columns={
                    "Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
                })
                df_hist["date"] = pd.to_datetime(df_hist["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
                df_ind = calculate_indicators_full(df_hist)
                df_ind["ticker"] = t
                cols = [
                    "ticker", "date", "open", "high", "low", "close", "volume",
                    "bb_sma_20", "bb_upper_20", "bb_lower_20", "rsi_14",
                    "macd", "macd_signal", "macd_hist", "buy_signal", "sell_signal"
                ]
                for c in cols:
                    if c not in df_ind.columns:
                        df_ind[c] = pd.NA
                out = df_ind[cols].copy()
                for c in ["open", "high", "low", "close"] + [c for c in NUMERIC_COLS if c in out.columns]:
                    out[c] = pd.to_numeric(out[c], errors="coerce").round(4)
                out["volume"] = out["volume"].fillna(0).astype("int64")
                out["buy_signal"] = out["buy_signal"].astype(bool)
                out["sell_signal"] = out["sell_signal"].astype(bool)
                frames.append(out)
            except Exception as e:
                print(f"[main] failed fetching {t}: {e}")
                continue
        if not frames:
            print("[main] no data fetched")
            return
        df = pd.concat(frames, ignore_index=True)

    print("[main] total rows prepared:", len(df))
    if df.empty:
        print("[main] nothing to upsert")
        return

    use_ddb = os.environ.get("USE_DYNAMODB", "0") == "1"
    if use_ddb:
        ddb_table = os.environ.get("DDB_TABLE")
        region = os.environ.get("AWS_REGION")
        if not ddb_table:
            print("[main] DDB_TABLE not set — not writing")
        else:
            upsert_dynamodb(df, ddb_table, region=region)
    else:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE") or os.environ.get("SUPABASE_KEY")
        supabase_table = os.environ.get("SUPABASE_TABLE", "stock_prices")
        if supabase_url and supabase_key:
            try:
                upsert_supabase(df, supabase_table, supabase_url, supabase_key)
            except Exception as e:
                print("[main] upsert_supabase failed:", e)
                raise
        else:
            print("[main] SUPABASE_URL or SUPABASE_KEY not set; printing sample rows instead")
            print(df.head().to_dict(orient="records"))


if __name__ == "__main__":
    main()
