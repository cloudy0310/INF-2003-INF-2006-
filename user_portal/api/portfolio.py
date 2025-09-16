# api/portfolio.py
from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from api.stock_analysis import get_stock_prices

def _drawdown(nav: pd.Series) -> pd.Series:
    peak = nav.cummax()
    return (nav / peak - 1.0).fillna(0.0)

def _annualize_return(total_return: float, num_days: int) -> float:
    if num_days <= 0:
        return np.nan
    yrs = num_days / 365.25
    if yrs <= 0:
        return np.nan
    return (1.0 + total_return) ** (1.0 / yrs) - 1.0

def _annualize_vol(daily_returns: pd.Series) -> float:
    return daily_returns.std(skipna=True) * np.sqrt(252)

def _sharpe(daily_returns: pd.Series, rf: float = 0.0) -> float:
    vol = _annualize_vol(daily_returns)
    if vol == 0 or np.isnan(vol):
        return np.nan
    ann_ret = (1 + daily_returns.mean()) ** 252 - 1
    return (ann_ret - rf) / vol

def _union_calendar(price_map: Dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    all_dates = pd.Index([])
    for df in price_map.values():
        if not df.empty:
            all_dates = all_dates.union(pd.to_datetime(df["date"]))
    return pd.DatetimeIndex(sorted(all_dates.unique()))

def compute_portfolio_history(
    items: List[Dict],                  # [{'ticker': 'AAPL', 'allocation': 10000.0}, ...]
    start: Optional[pd.Timestamp | str] = None,
    end: Optional[pd.Timestamp | str] = None,
    benchmark_ticker: Optional[str] = None,
) -> Dict:
    """
    Returns dict:
      nav: DataFrame[date, nav]
      bench: DataFrame[date, bench_nav] or None
      metrics: dict
      contrib: DataFrame[ticker, start_val, end_val, pnl_abs, pnl_pct_of_total]
      weights_current: DataFrame[ticker, weight_now_pct]
      corr: DataFrame (ticker x ticker correlations)
      drawdown: DataFrame[date, drawdown]
    """
    items = [it for it in (items or []) if float(it.get("allocation") or 0) > 0]
    out = {"nav": None, "bench": None, "metrics": {}, "contrib": None, "weights_current": None, "corr": None, "drawdown": None}
    if not items:
        return out

    # 1) Load prices for each ticker (from your stock_prices via get_stock_prices)
    price_map: Dict[str, pd.DataFrame] = {}
    for it in items:
        t = (it["ticker"] or "").upper().strip()
        if not t:
            continue
        df = get_stock_prices(t, start=str(start) if start else None, end=str(end) if end else None, limit=100000)
        if not df.empty:
            df = df[["date", "close"]].dropna().copy()
            df["date"] = pd.to_datetime(df["date"])
            df.sort_values("date", inplace=True)
            price_map[t] = df
    if not price_map:
        return out

    # 2) Build union calendar and forward-fill closes
    cal = _union_calendar(price_map)
    if len(cal) == 0:
        return out

    close_map: Dict[str, pd.Series] = {}
    shares_map: Dict[str, float] = {}

    for it in items:
        t = (it["ticker"] or "").upper().strip()
        alloc = float(it["allocation"] or 0.0)
        if t not in price_map or alloc <= 0:
            continue
        df = price_map[t].set_index("date").reindex(cal)
        df["close"] = df["close"].ffill()
        first_idx = df["close"].first_valid_index()
        if first_idx is None:
            continue
        entry_price = float(df.loc[first_idx, "close"])
        if entry_price <= 0:
            continue
        shares_map[t] = alloc / entry_price
        close_map[t] = df["close"]

    if not shares_map:
        return out

    # 3) Per-ticker values and portfolio NAV
    values = {t: s * close_map[t] for t, s in shares_map.items()}
    df_val = pd.DataFrame(values, index=cal).sort_index().ffill().fillna(0.0)
    nav = df_val.sum(axis=1)
    nav_df = pd.DataFrame({"date": nav.index, "nav": nav.values})
    out["nav"] = nav_df

    # 4) Metrics
    if len(nav) >= 2:
        total_return = nav.iloc[-1] / nav.iloc[0] - 1.0
        days = (nav.index[-1] - nav.index[0]).days
        ann_ret = _annualize_return(total_return, days)
        daily = nav.pct_change().dropna()
        vol = _annualize_vol(daily)
        sharpe = _sharpe(daily)
        dd = _drawdown(nav)
        out["metrics"] = {
            "days": int(days),
            "total_return_pct": float(total_return * 100),
            "annualized_return_pct": float(ann_ret * 100) if pd.notna(ann_ret) else None,
            "volatility_pct": float(vol * 100) if pd.notna(vol) else None,
            "sharpe": float(sharpe) if pd.notna(sharpe) else None,
            "max_drawdown_pct": float(dd.min() * 100),
        }
        out["drawdown"] = pd.DataFrame({"date": dd.index, "drawdown": dd.values})

    # 5) Contributions
    start_vals = {t: float(df_val[t].iloc[0]) for t in df_val.columns}
    end_vals   = {t: float(df_val[t].iloc[-1]) for t in df_val.columns}
    pnl_abs    = {t: end_vals[t] - start_vals[t] for t in df_val.columns}
    total_pnl  = sum(pnl_abs.values()) or 1.0
    contrib = pd.DataFrame({
        "ticker": df_val.columns,
        "start_val": [start_vals[t] for t in df_val.columns],
        "end_val": [end_vals[t] for t in df_val.columns],
        "pnl_abs": [pnl_abs[t] for t in df_val.columns],
    }).sort_values("pnl_abs", ascending=False)
    contrib["pnl_pct_of_total"] = (contrib["pnl_abs"] / total_pnl) * 100.0
    out["contrib"] = contrib

    # 6) Current weights
    if nav.iloc[-1] > 0:
        w = (df_val.iloc[-1] / nav.iloc[-1]).sort_values(ascending=False)
        out["weights_current"] = pd.DataFrame({"ticker": w.index, "weight_now_pct": w.values * 100.0})

    # 7) Correlations
    if df_val.shape[1] >= 2:
        ret_mat = df_val.pct_change().dropna(how="all").fillna(0.0)
        if not ret_mat.empty:
            out["corr"] = ret_mat.corr()

    # 8) Optional benchmark (from your DB via get_stock_prices)
    if benchmark_ticker:
        b = (benchmark_ticker or "").upper().strip()
        bprices = get_stock_prices(b, start=str(nav.index[0].date()), end=str(nav.index[-1].date()), limit=100000)
        if not bprices.empty:
            bser = bprices[["date", "close"]].dropna().copy()
            bser["date"] = pd.to_datetime(bser["date"])
            bser = bser.set_index("date").reindex(nav.index).ffill().dropna()
            if not bser.empty:
                bench_nav = bser["close"] / float(bser["close"].iloc[0]) * float(nav.iloc[0])
                out["bench"] = pd.DataFrame({"date": bench_nav.index, "bench_nav": bench_nav.values})

    return out
