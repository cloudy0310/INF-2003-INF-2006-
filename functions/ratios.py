# stock_tool/ratios.py
import pandas as pd
import numpy as np

def safe_latest(df: pd.DataFrame, field_name: str):
    if isinstance(df, pd.DataFrame) and not df.empty:
        # yfinance returns columns as dates; pick the first (most recent) column
        try:
            return df.iloc[:, 0].dropna().astype(float)
        except Exception:
            return np.nan
    return np.nan

def compute_key_ratios(info: dict, financials: dict):
    """
    Build a flat dict of common ratios. Use info first and then compute from
    financial statements where possible. Handle missing data gracefully.
    """
    ratios = {}
    inf = info or {}
    # Basic market stats
    ratios["marketCap"] = inf.get("marketCap")
    ratios["beta"] = inf.get("beta")
    ratios["sharesOutstanding"] = inf.get("sharesOutstanding")
    ratios["trailingPE"] = inf.get("trailingPE")
    ratios["forwardPE"] = inf.get("forwardPE")
    ratios["trailingEps"] = inf.get("trailingEps")
    ratios["priceToBook"] = inf.get("priceToBook")
    ratios["priceToSalesTrailing12Months"] = inf.get("priceToSalesTrailing12Months")
    ratios["enterpriseValue"] = inf.get("enterpriseValue")

    # Use financial statements
    fin = financials.get("financials") if financials else None
    bal = financials.get("balance_sheet") if financials else None
    cash = financials.get("cashflow") if financials else None

    # Net income, revenue from income statement (most recent column)
    try:
        net_income = safe_latest(fin, "Net Income") if isinstance(fin, (pd.DataFrame,)) else np.nan
    except Exception:
        net_income = np.nan
    try:
        revenue = safe_latest(fin, "Total Revenue") if isinstance(fin, (pd.DataFrame,)) else np.nan
    except Exception:
        revenue = np.nan

    # Totals from balance sheet
    try:
        total_assets = safe_latest(bal, "Total Assets") if isinstance(bal, (pd.DataFrame,)) else np.nan
    except Exception:
        total_assets = np.nan
    try:
        total_liab = safe_latest(bal, "Total Liab") if isinstance(bal, (pd.DataFrame,)) else np.nan
    except Exception:
        total_liab = np.nan
    try:
        cash_and_eq = safe_latest(bal, "Cash") if isinstance(bal, (pd.DataFrame,)) else np.nan
    except Exception:
        cash_and_eq = np.nan

    # Common ratios (guard divide by zero)
    def _safe_div(a, b):
        try:
            a = float(a)
            b = float(b)
            return a / b if b != 0 and not pd.isna(b) else None
        except Exception:
            return None

    ratios["net_margin"] = _safe_div(net_income, revenue)
    ratios["debt_to_assets"] = _safe_div(total_liab, total_assets)
    ratios["current_ratio"] = None  # yfinance balance sheet doesn't separate current assets/liabilities consistently
    ratios["cash_ratio"] = _safe_div(cash_and_eq, total_liab)
    ratios["roa"] = _safe_div(net_income, total_assets)
    # Return as flat dict
    return ratios
