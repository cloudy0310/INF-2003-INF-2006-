from __future__ import annotations
from typing import Optional, Dict, Any
import os
import pandas as pd
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    import boto3
    from botocore.config import Config
    from boto3.dynamodb.conditions import Key
except Exception:
    boto3 = None

# Load .env and override any existing process envs
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=True)
except Exception:
    pass

# ---------- ENV ----------
RDS_HOST = os.getenv("RDS_HOST")
RDS_PORT = int(os.getenv("RDS_PORT", "5432"))
RDS_DB   = os.getenv("RDS_DB")
RDS_USER = os.getenv("RDS_USER")
RDS_PWD  = os.getenv("RDS_PASSWORD")

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
DDB_TABLE_STOCK_PRICES = os.getenv("DDB_TABLE_STOCK_PRICES", "stock_prices")

# ---------- CONNECTION HELPERS ----------
_ENGINE: Optional[Engine] = None
_DDB_TABLE = None

def get_rds_engine() -> Engine:
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    missing = [k for k, v in {
        "RDS_HOST": RDS_HOST, "RDS_DB": RDS_DB, "RDS_USER": RDS_USER, "RDS_PASSWORD": RDS_PWD
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Missing RDS env vars: {', '.join(missing)}")
    url = f"postgresql+psycopg2://{RDS_USER}:{RDS_PWD}@{RDS_HOST}:{RDS_PORT}/{RDS_DB}"
    _ENGINE = create_engine(url, pool_pre_ping=True)
    return _ENGINE

def _clean_env(name: str) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return None
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]
    return v

def _assert_aws_creds_present():
    akid   = _clean_env("AWS_ACCESS_KEY_ID") or ""
    secret = _clean_env("AWS_SECRET_ACCESS_KEY") or ""
    token  = _clean_env("AWS_SESSION_TOKEN") or ""
    problems = []
    if len(akid) < 16:
        problems.append(f"AWS_ACCESS_KEY_ID looks too short (len={len(akid)})")
    if len(secret) < 20:
        problems.append(f"AWS_SECRET_ACCESS_KEY looks too short (len={len(secret)})")
    if akid.startswith("ASIA") and not token:
        problems.append("AWS_SESSION_TOKEN missing for temporary ASIA keys")
    if problems:
        raise RuntimeError("Bad AWS credentials: " + "; ".join(problems))

def _make_boto3_session():
    for key in ["AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN","AWS_REGION","AWS_DEFAULT_REGION"]:
        val = _clean_env(key)
        if val is not None:
            os.environ[key] = val

    _assert_aws_creds_present()

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-1"
    if region.endswith(("a","b","c","d","e","f","g")) and region.count("-") == 2:
        region = region.rsplit("-", 1)[0]
        os.environ["AWS_REGION"] = region

    cfg = Config(region_name=region, retries={"max_attempts": 10, "mode": "adaptive"})
    return boto3.session.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN") or None,
        region_name=region
    ), cfg

def get_ddb_table():
    global _DDB_TABLE
    if _DDB_TABLE is not None:
        return _DDB_TABLE
    if boto3 is None:
        raise RuntimeError("boto3 not installed")
    sess, cfg = _make_boto3_session()
    sess.client("sts", config=cfg).get_caller_identity()
    ddb_res = sess.resource("dynamodb", region_name=sess.region_name)
    _DDB_TABLE = ddb_res.Table(DDB_TABLE_STOCK_PRICES)
    return _DDB_TABLE

# ---------- RDS QUERIES ----------
def get_company_info(ticker: str) -> Optional[dict]:
    eng = get_rds_engine()
    sql = text("""
        SELECT *
        FROM public.companies
        WHERE ticker = :ticker
        LIMIT 1
    """)
    with eng.connect() as conn:
        row = conn.execute(sql, {"ticker": ticker}).mappings().first()
        return dict(row) if row else None

def get_financials(ticker: str) -> pd.DataFrame:
    eng = get_rds_engine()
    sql = text("""
        SELECT *
        FROM public.financials
        WHERE ticker = :ticker
        ORDER BY period_end DESC
    """)
    with eng.connect() as conn:
        df = pd.read_sql_query(sql, conn, params={"ticker": ticker})
    return df

# ---------- DDB: STOCK PRICES ----------
def _coerce_decimal(obj: Any):
    if isinstance(obj, list):
        return [_coerce_decimal(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _coerce_decimal(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    return obj

def _to_bool(val: Any) -> bool:
    truey = {True, "true", "True", "TRUE", "t", "T", "1", 1}
    falsy = {False, "false", "False", "FALSE", "f", "F", "0", 0, None}
    if val in truey:
        return True
    if val in falsy:
        return False
    return False

def get_stock_prices(ticker: str, start: str = None, end: str = None, limit: int = 10000) -> pd.DataFrame:
    table = get_ddb_table()
    start_key = start or "0000-01-01"
    end_key   = end or "9999-12-31"
    kwargs: Dict[str, Any] = {
        "KeyConditionExpression": Key("ticker").eq(ticker) & Key("date").between(start_key, end_key),
        "ScanIndexForward": True
    }
    if limit and limit > 0:
        kwargs["Limit"] = limit

    items = []
    resp = table.query(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp and (not limit or len(items) < limit):
        next_kwargs = dict(kwargs)
        next_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        if limit:
            next_kwargs["Limit"] = max(1, limit - len(items))
        resp = table.query(**next_kwargs)
        items.extend(resp.get("Items", []))

    if not items:
        return pd.DataFrame()

    df = pd.DataFrame([_coerce_decimal(i) for i in items])
    if "date" not in df.columns:
        raise RuntimeError("DynamoDB item missing 'date' attribute")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    numeric_cols = [
        "open","high","low","close","volume",
        "bb_sma_20","bb_upper_20","bb_lower_20",
        "rsi_14","macd","macd_signal","macd_hist"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["buy_signal", "sell_signal"]:
        if col in df.columns:
            df[col] = df[col].map(_to_bool)
        else:
            df[col] = False

    df = df.sort_values("date").reset_index(drop=True)
    if all(c in df.columns for c in ["open","high","low","close"]):
        df = df.dropna(subset=["open","high","low","close"])
    return df
