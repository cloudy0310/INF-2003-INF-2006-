# functions/watchlist.py
from pathlib import Path
from typing import Optional
import pandas as pd
import os
import tempfile
import time

DB_DIR = Path("db")
DB_DIR.mkdir(parents=True, exist_ok=True)
WATCHLIST_CSV = DB_DIR / "watchlist.csv"


def _atomic_write_csv(path: Path, df: pd.DataFrame) -> None:
    """
    Write CSV atomically to avoid partial writes (write to temp + replace).
    Keeps index=False.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    os.close(fd)
    try:
        # Use to_csv on the temp path
        df.to_csv(tmp_path, index=False)
        # Atomic replace on most OSes
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def load_watchlist() -> pd.DataFrame:
    """
    Returns DataFrame with columns: ticker (str), added_at (datetime64[ns, UTC]), amount (float or NaN)
    If file missing, returns empty DataFrame with those columns.
    """
    if not WATCHLIST_CSV.exists():
        return pd.DataFrame(columns=["ticker", "added_at", "amount"])

    try:
        df = pd.read_csv(WATCHLIST_CSV)
    except Exception:
        # fallback: return empty
        return pd.DataFrame(columns=["ticker", "added_at", "amount"])

    # ensure expected columns
    for col in ["ticker", "added_at", "amount"]:
        if col not in df.columns:
            df[col] = pd.NA

    # normalize ticker to uppercase, coerce amount to float
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    # parse added_at as UTC datetimes if possible
    try:
        df["added_at"] = pd.to_datetime(df["added_at"], utc=True, errors="coerce")
    except Exception:
        df["added_at"] = pd.NaT

    # coerce amount
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    # drop duplicates keeping last (so a re-add will update timestamp/amount)
    df = df.drop_duplicates(subset=["ticker"], keep="last").reset_index(drop=True)
    return df[["ticker", "added_at", "amount"]]


def save_watchlist(df: pd.DataFrame) -> None:
    """
    Save watchlist DataFrame to CSV (atomic). Ensures columns order and types.
    """
    df_out = df.copy()
    # ensure columns
    df_out = df_out[["ticker", "added_at", "amount"]]
    # Convert added_at to ISO strings for CSV portability
    df_out["added_at"] = df_out["added_at"].apply(lambda ts: ts.isoformat() if pd.notna(ts) else "")
    _atomic_write_csv(WATCHLIST_CSV, df_out)


def add_to_watchlist(ticker: str, amount: Optional[float] = None) -> pd.DataFrame:
    ticker = ticker.strip().upper()
    if not ticker:
        return load_watchlist()

    df = load_watchlist()
    now = pd.Timestamp.now(tz="UTC")   # ✅ fixed here
    if ticker in df["ticker"].values:
        df.loc[df["ticker"] == ticker, "added_at"] = now
        if amount is not None:
            df.loc[df["ticker"] == ticker, "amount"] = float(amount)
    else:
        new_row = {"ticker": ticker, "added_at": now, "amount": float(amount) if amount is not None else pd.NA}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    save_watchlist(df)
    return load_watchlist()



def remove_from_watchlist(ticker: str) -> pd.DataFrame:
    """
    Remove a ticker from the watchlist. Returns the updated DataFrame.
    """
    ticker = ticker.strip().upper()
    df = load_watchlist()
    if ticker in df["ticker"].values:
        df = df[df["ticker"] != ticker].reset_index(drop=True)
        save_watchlist(df)
    return load_watchlist()


def update_amount(ticker: str, amount: Optional[float]) -> pd.DataFrame:
    """
    Update only the amount for a ticker. If ticker missing, does nothing.
    """
    ticker = ticker.strip().upper()
    df = load_watchlist()
    if ticker in df["ticker"].values:
        df.loc[df["ticker"] == ticker, "amount"] = float(amount) if amount is not None else pd.NA
        save_watchlist(df)
    return load_watchlist()
