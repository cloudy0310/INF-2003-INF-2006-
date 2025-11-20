import os
import boto3
import yfinance as yf
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime

S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "raw/")
TICKERS = os.environ["TICKERS"].split(",")
HISTORICAL_PERIOD = os.environ.get("HISTORICAL_PERIOD", "1y")

s3 = boto3.client("s3")

def lambda_handler(event, context):
    for t in TICKERS:
        t = t.strip().upper()
        if not t:
            continue

        try:
            tk = yf.Ticker(t)
            df = tk.history(period=HISTORICAL_PERIOD, auto_adjust=False)

            if df.empty:
                print(f"No data for {t}")
                continue

            df = df.reset_index()
            df["Ticker"] = t

            table = pa.Table.from_pandas(df)
            buf = pa.BufferOutputStream()
            pq.write_table(table, buf)

            date_key = datetime.utcnow().strftime("%Y-%m-%d")
            key = f"{S3_PREFIX}ticker={t}/{date_key}.parquet"

            s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=buf.getvalue().to_pybytes()
            )

            print(f"Saved {t} → s3://{S3_BUCKET}/{key}")

        except Exception as e:
            print(f"Error for {t}: {e}")

    return {"status": "done"}
