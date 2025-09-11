# functions/fetch_data.py
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
import yfinance as yf
import time
import json
import os
import tempfile
import pandas.api.types as ptypes

DB_DIR = Path("db")
DB_DIR.mkdir(parents=True, exist_ok=True)


def ticker_obj(ticker: str) -> yf.Ticker:
    return yf.Ticker(ticker.upper())


# -----------------------
# Helpers: detect datetime-like index
# -----------------------
def _looks_like_datetime_index(index, min_success_ratio: float = 0.5) -> bool:
    """
    Heuristic: return True if index is already datetime dtype, or if attempting to parse
    the index yields >= min_success_ratio non-NaT values.
    """
    # If it's already a datetime64 or tz-aware datetime index, accept it.
    try:
        if ptypes.is_datetime64_any_dtype(index) or ptypes.is_datetime64tz_dtype(index):
            return True
    except Exception:
        pass

    # If it's empty, treat as not datetime-like
    if len(index) == 0:
        return False

    # Try parsing as datetimes (UTC) and check fraction parsed
    parsed = pd.to_datetime(index, utc=True, errors="coerce")
    success = parsed.notna().sum()
    return (success / max(1, len(index))) >= min_success_ratio


# -----------------------
# Atomic write / safe read
# -----------------------
def _write_csv_atomic(path: Path, df: pd.DataFrame) -> None:
    """
    Atomically write df to CSV at path.

    Behavior:
      - If the DataFrame index appears to be datetime-like, normalize it to tz-aware UTC and
        save ISO strings as the index (portable).
      - Otherwise, write index as-is.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Decide whether to treat index as datetime-like
    treat_index_as_dt = _looks_like_datetime_index(df.index, min_success_ratio=0.5)

    df_to_save = df.copy()

    if treat_index_as_dt:
        try:
            # Convert/index to UTC-aware DatetimeIndex
            idx = pd.to_datetime(df_to_save.index, utc=True, errors="coerce")
            # If there are NaT values (rare), leave them as-is but still use ISO strings for others
            # give the index a name
            df_to_save.index = idx
            df_to_save.index.name = "date"
            # Represent index as ISO strings for portability when writing CSV
            df_to_save.index = df_to_save.index.map(lambda ts: ts.isoformat() if pd.notna(ts) else "")
        except Exception:
            # fallback: stringify index
            df_to_save.index = df_to_save.index.astype(str)
            df_to_save.index.name = "date"
    else:
        # Non-datetime index -> keep as-is but ensure index has a name so CSV column header is stable
        if df_to_save.index.name is None:
            df_to_save.index.name = "index"

    # Write to temp file then atomically replace
    fd, tmp_path = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    os.close(fd)
    try:
        # use to_csv on tmp_path (string)
        df_to_save.to_csv(tmp_path, index=True)
        # Atomic replace
        os.replace(tmp_path, str(path))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _read_csv_safe(path: Path) -> Optional[pd.DataFrame]:
    """
    Read CSV and attempt to parse index as tz-aware UTC datetimes *only* if it looks like a datetime index.
    Returns None on failure to read the file.
    """
    if not path.exists():
        return None
    try:
        # don't force parse_dates here; read raw and decide
        df = pd.read_csv(path, index_col=0)
    except Exception:
        return None

    if df is None or df.empty:
        return df

    # Decide whether index looks like datetimes
    try:
        idx_vals = df.index
        if _looks_like_datetime_index(idx_vals, min_success_ratio=0.5):
            # parse as UTC-aware datetimes first
            parsed = pd.to_datetime(idx_vals, utc=True, errors="coerce")

            # If parsing produced NaT for all, try without utc
            if parsed.isna().all():
                parsed = pd.to_datetime(idx_vals, errors="coerce")
                if getattr(parsed, "tz", None) is None:
                    # naive → localize to UTC
                    parsed = parsed.tz_localize("UTC")
                else:
                    # already tz-aware → convert to UTC
                    parsed = parsed.tz_convert("UTC")

            df.index = parsed
            df.index.name = "date"
        else:
            # keep original index as-is (likely company info or RangeIndex string)
            if df.index.name is None:
                df.index.name = "index"
    except Exception:
        # fail-safe: return raw df (no index parsing)
        if df.index.name is None:
            df.index.name = "index"

    return df



# -----------------------
# Price history fetching
# -----------------------
def fetch_price_history(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    force_refresh: bool = False,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    ticker_sym = ticker.upper()
    csv_path = DB_DIR / f"{ticker_sym}_price.csv"

    # Try to use cached CSV first (extend if possible)
    if csv_path.exists() and not force_refresh:
        existing = _read_csv_safe(csv_path)
        if existing is not None and not existing.empty:
            existing = existing.sort_index()
            last_date = existing.index.max()
            # ensure datetime-like for comparison
            try:
                last_date = pd.to_datetime(last_date, utc=True)
                last_date = last_date.normalize()
            except Exception:
                last_date = existing.index.max()  # fallback, may be non-dt

            today = pd.Timestamp.now(tz="UTC").normalize()

            # If cached file covers today -> return
            try:
                if last_date >= today:
                    return existing
            except Exception:
                # if comparison fails, continue to fetch full history below
                pass

            # fetch tail from last_date +1 day (convert to date string)
            try:
                fetch_start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                fetch_start = None

            try:
                t = ticker_obj(ticker_sym)
                if fetch_start:
                    new = t.history(start=fetch_start, end=None, interval=interval, actions=False)
                else:
                    new = t.history(period=period, interval=interval, actions=False)
            except Exception:
                new = pd.DataFrame()

            if new is not None and not new.empty:
                new = new.rename(columns=lambda c: c.lower())
                new.index = pd.to_datetime(new.index, utc=True)
                new.index.name = "date"
                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in new.columns]
                new = new.loc[:, cols]
                combined = pd.concat([existing, new])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                _write_csv_atomic(csv_path, combined)
                return combined

            return existing

    # Otherwise fetch full range
    t = ticker_obj(ticker_sym)
    try:
        if start or end:
            hist = t.history(start=start, end=end, interval=interval, actions=False)
        else:
            hist = t.history(period=period, interval=interval, actions=False)
    except Exception as e:
        raise ValueError(f"Error fetching price history for {ticker_sym}: {e}")

    if hist is None or hist.empty:
        raise ValueError(f"No price history returned for {ticker_sym} (period={period}, start={start}, end={end}).")

    hist = hist.rename(columns=lambda c: c.lower())
    hist.index = pd.to_datetime(hist.index, utc=True)
    hist.index.name = "date"
    cols_keep = [c for c in ["open", "high", "low", "close", "volume"] if c in hist.columns]
    hist = hist.loc[:, cols_keep]
    hist = hist.sort_index()
    _write_csv_atomic(csv_path, hist)
    return hist


# -----------------------
# save/load helpers
# -----------------------
def save_indicators(ticker: str, df: pd.DataFrame, suffix: str = "indicators") -> Path:
    ticker_sym = ticker.upper()
    csv_path = DB_DIR / f"{ticker_sym}_{suffix}.csv"
    _write_csv_atomic(csv_path, df)
    return csv_path


def load_csv_if_exists(path: Path) -> Optional[pd.DataFrame]:
    return _read_csv_safe(path)


# -----------------------
# Company info caching
# -----------------------
def save_company_info(ticker: str, info: Dict[str, Any]) -> Path:
    ticker_sym = ticker.upper()
    csv_path = DB_DIR / f"{ticker_sym}_company.csv"
    try:
        df = pd.json_normalize(info)
        df = df.reindex(sorted(df.columns), axis=1)
        _write_csv_atomic(csv_path, df)
    except Exception:
        text_path = DB_DIR / f"{ticker_sym}_company.json"
        with open(text_path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        csv_path = text_path
    return csv_path


def fetch_company_info_cached(ticker: str, force_refresh: bool = False, max_age_days: int = 7) -> Dict[str, Any]:
    ticker_sym = ticker.upper()
    csv_path = DB_DIR / f"{ticker_sym}_company.csv"
    json_path = DB_DIR / f"{ticker_sym}_company.json"

    if not force_refresh:
        if csv_path.exists():
            age_seconds = time.time() - os.path.getmtime(csv_path)
            if age_seconds <= max_age_days * 86400:
                df = _read_csv_safe(csv_path)
                if df is not None and not df.empty:
                    # convert single-row df to dict
                    return df.iloc[0].to_dict()
        if json_path.exists():
            age_seconds = time.time() - os.path.getmtime(json_path)
            if age_seconds <= max_age_days * 86400:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

    t = ticker_obj(ticker_sym)
    try:
        info = t.info or {}
    except Exception:
        info = {}

    save_company_info(ticker_sym, info)
    return info


# -----------------------
# News caching
# -----------------------
def _news_list_to_df(news_list: list) -> pd.DataFrame:
    if not news_list:
        return pd.DataFrame()
    rows = []
    for item in news_list:
        title = item.get("title") or item.get("headline") or ""
        publisher = item.get("publisher") or item.get("provider") or item.get("source") or ""
        link = item.get("link") or item.get("itemLink") or ""
        ppt = item.get("providerPublishTime") or item.get("published") or None
        try:
            if ppt is not None:
                dt = pd.to_datetime(int(ppt), unit="s", utc=True)
            else:
                dt = None
        except Exception:
            try:
                dt = pd.to_datetime(ppt, utc=True)
            except Exception:
                dt = None
        rows.append({
            "title": title,
            "publisher": publisher,
            "link": link,
            "providerPublishTime": ppt,
            "datetime": dt
        })
    df = pd.DataFrame(rows)
    if "datetime" in df.columns and not df["datetime"].isna().all():
        df = df.sort_values("datetime", ascending=False).reset_index(drop=True)
    return df


def fetch_news_cached(ticker: str, force_refresh: bool = False, max_age_hours: int = 6) -> pd.DataFrame:
    ticker_sym = ticker.upper()
    csv_path = DB_DIR / f"{ticker_sym}_news.csv"

    if not force_refresh and csv_path.exists():
        age_seconds = time.time() - os.path.getmtime(csv_path)
        if age_seconds <= max_age_hours * 3600:
            df_cached = _read_csv_safe(csv_path)
            if df_cached is not None:
                return df_cached

    t = ticker_obj(ticker_sym)
    try:
        raw_news = t.news
    except Exception:
        raw_news = []

    if not raw_news:
        if csv_path.exists():
            df_cached = _read_csv_safe(csv_path)
            if df_cached is not None:
                return df_cached
        return pd.DataFrame()

    df_news = _news_list_to_df(raw_news)
    if "datetime" in df_news.columns:
        df_news["datetime"] = df_news["datetime"].apply(lambda x: x.isoformat() if pd.notna(x) else "")
    _write_csv_atomic(csv_path, df_news)
    return df_news


# -----------------------
# Financial statements
# -----------------------
def fetch_financial_statements(ticker: str) -> Dict[str, pd.DataFrame]:
    t = ticker_obj(ticker)
    try:
        fin = t.financials if t.financials is not None else pd.DataFrame()
    except Exception:
        fin = pd.DataFrame()
    try:
        bal = t.balance_sheet if t.balance_sheet is not None else pd.DataFrame()
    except Exception:
        bal = pd.DataFrame()
    try:
        cash = t.cashflow if t.cashflow is not None else pd.DataFrame()
    except Exception:
        cash = pd.DataFrame()
    return {"financials": fin, "balance_sheet": bal, "cashflow": cash}


# -----------------------
# Pipeline runner: fetch -> compute -> save
# -----------------------
def run_fetch_compute_save(ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
    from functions import indicators as indicators_mod

    ticker_sym = ticker.upper()
    hist = fetch_price_history(ticker_sym, period="5y", interval="1d", force_refresh=force_refresh)

    try:
        ind_df = indicators_mod.add_all_indicators(hist.copy())
    except Exception:
        ind_df = hist.copy()

    _write_csv_atomic(DB_DIR / f"{ticker_sym}_price.csv", hist)
    _write_csv_atomic(DB_DIR / f"{ticker_sym}_indicators.csv", ind_df)

    info = fetch_company_info_cached(ticker_sym, force_refresh=force_refresh)
    news_df = fetch_news_cached(ticker_sym, force_refresh=force_refresh)

    return {"history": hist, "indicators": ind_df, "info": info, "news": news_df}
