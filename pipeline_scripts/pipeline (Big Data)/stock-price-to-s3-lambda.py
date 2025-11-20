import os
import boto3
import yfinance as yf
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime

S3_BUCKET = os.environ["S3_BUCKET"]
RAW_PREFIX = os.environ.get("RAW_PREFIX", "raw/")
TICKERS = os.environ.get("TICKERS", "").split(",")
HISTORICAL_PERIOD = os.environ.get("HISTORICAL_PERIOD", "1y")

s3 = boto3.client("s3")

# ---------------------------------------------
# Indicator Calculations
# ---------------------------------------------
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("Date").reset_index(drop=True)

    # MACD
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # RSI
    delta = df["Close"].diff(1)
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    sma = df["Close"].rolling(20).mean()
    std = df["Close"].rolling(20).std()
    df["bb_sma_20"] = sma
    df["bb_upper_20"] = sma + 2 * std
    df["bb_lower_20"] = sma - 2 * std

    return df


# ---------------------------------------------
# Lambda Handler: Fetch → Indicators → Parquet → S3
# ---------------------------------------------
def lambda_handler(event, context):
    processed = 0

    for t in TICKERS:
        t = t.strip().upper()
        if not t:
            continue

        try:
            print(f"Fetching {t}...")
            tk = yf.Ticker(t)
            df = tk.history(period=HISTORICAL_PERIOD, auto_adjust=False)

            if df.empty:
                print(f"[WARN] No data for {t}")
                continue

            df = df.reset_index()
            df["Ticker"] = t

            df = calculate_indicators(df)

            # Convert to Parquet buffer
            table = pa.Table.from_pandas(df)
            buf = pa.BufferOutputStream()
            pq.write_table(table, buf)

            # S3 path: raw/ticker=AAPL/2025-01-01.parquet
            date_key = datetime.utcnow().strftime("%Y-%m-%d")
            s3_key = f"{RAW_PREFIX}ticker={t}/{date_key}.parquet"

            s3.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=buf.getvalue().to_pybytes()
            )

            print(f"Uploaded → s3://{S3_BUCKET}/{s3_key}")
            processed += 1

        except Exception as e:
            print(f"[ERROR] {t}: {e}")

    return {
        "status": "success",
        "tickers_processed": processed
    }
