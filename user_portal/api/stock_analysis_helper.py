# api/stock_analysis_helper.py
"""
Trading calculation helper with cluster-based case selection.

Key behavior:
- recompute signals (BB, RSI, MACD) from close price given knobs
- cluster buy/sell signals by date proximity (cluster_gap_days)
- for each buy-cluster, choose an index:
    - min: earliest (0th quantile)
    - average: median (50th percentile)
    - greedy: late (75th percentile)
  and pair with the next sell-cluster (selected by same quantile for that case)
- produce trades for all buy clusters sequentially (non-overlapping)
- compute metrics and step equity curve
"""
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np


# --------------------------
# Indicators
# --------------------------
def compute_bollinger(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    close = df["close"]
    sma = close.rolling(window=window, min_periods=1).mean()
    std = close.rolling(window=window, min_periods=1).std(ddof=0).fillna(0.0)
    upper = sma + 2.0 * std
    lower = sma - 2.0 * std
    df["bb_sma"] = sma
    df["bb_upper"] = upper
    df["bb_lower"] = lower
    return df


def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = df["close"].diff()
    up = delta.clip(lower=0.0)
    down = -1.0 * delta.clip(upper=0.0)
    ema_up = up.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()
    ema_down = down.ewm(alpha=1.0/period, adjust=False, min_periods=period).mean()
    rs = ema_up / (ema_down.replace(0, np.nan))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    df["rsi"] = rsi.fillna(50.0)
    return df


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    close = df["close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    df["macd"] = macd
    df["macd_signal"] = macd_signal
    df["macd_hist"] = macd_hist
    return df


# --------------------------
# Signal recompute
# --------------------------
def recompute_signals(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """
    Compute indicators and buy/sell booleans using knobs in params.
    Params keys:
      - bb_window (int), default 20
      - rsi_buy (float), default 35
      - rsi_sell (float), default 70
      - macd_hist_threshold (float), default 0.0
      - require_all (bool), default True (require all conditions for buy)
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"])
    if df.empty:
        df["buy_signal"] = False
        df["sell_signal"] = False
        return df

    bb_window = int(params.get("bb_window", 20))
    rsi_buy = float(params.get("rsi_buy", 35.0))
    rsi_sell = float(params.get("rsi_sell", 70.0))
    macd_hist_threshold = float(params.get("macd_hist_threshold", 0.0))
    require_all = bool(params.get("require_all", True))

    df = compute_bollinger(df, window=bb_window)
    df = compute_rsi(df, period=14)
    df = compute_macd(df, fast=12, slow=26, signal=9)

    df["macd_hist_prev"] = df["macd_hist"].shift(1).fillna(0.0)

    cond_bb_below = df["close"] < df["bb_lower"]
    cond_bb_above = df["close"] > df["bb_upper"]
    cond_rsi_buy = df["rsi"] < rsi_buy
    cond_rsi_sell = df["rsi"] > rsi_sell
    cond_macd_buy = (df["macd_hist"] > macd_hist_threshold) & (df["macd_hist_prev"] <= macd_hist_threshold)
    cond_macd_sell = df["macd_hist"] < macd_hist_threshold

    if require_all:
        df["buy_signal"] = (cond_bb_below & cond_rsi_buy & cond_macd_buy).fillna(False).astype(bool)
        df["sell_signal"] = (cond_bb_above | cond_rsi_sell | cond_macd_sell).fillna(False).astype(bool)
    else:
        buy_votes = (cond_bb_below.astype(int) + cond_rsi_buy.astype(int) + cond_macd_buy.astype(int))
        sell_votes = (cond_bb_above.astype(int) + cond_rsi_sell.astype(int) + cond_macd_sell.astype(int))
        df["buy_signal"] = (buy_votes >= 2).fillna(False).astype(bool)
        df["sell_signal"] = (sell_votes >= 2).fillna(False).astype(bool)

    df = df.drop(columns=["macd_hist_prev"], errors="ignore")
    return df


# --------------------------
# Clustering utility
# --------------------------
def cluster_indices_by_date(df: pd.DataFrame, indices: List[int], max_gap_days: int = 3) -> List[List[int]]:
    """
    Group a sorted list of indices into clusters where date gaps between successive indices
    are <= max_gap_days. Returns list of clusters (each is a list of indices sorted ascending).
    """
    if not indices:
        return []

    clusters: List[List[int]] = []
    current = [indices[0]]
    for idx in indices[1:]:
        prev_idx = current[-1]
        prev_date = pd.to_datetime(df.loc[prev_idx, "date"])
        cur_date = pd.to_datetime(df.loc[idx, "date"])
        gap = (cur_date - prev_date).days
        if gap <= max_gap_days:
            current.append(idx)
        else:
            clusters.append(current)
            current = [idx]
    clusters.append(current)
    return clusters


def select_index_from_cluster(df: pd.DataFrame, cluster: List[int], quantile: float = 0.5) -> int:
    """
    Given a cluster (list of indices sorted by date), choose an index by quantile:
    - quantile=0.0 -> earliest
    - quantile=0.5 -> median
    - quantile=0.75 -> late
    We compute position = round(q * (n-1)) and return cluster[pos].
    """
    n = len(cluster)
    if n == 0:
        raise ValueError("Empty cluster")
    pos = int(round(quantile * (n - 1)))
    pos = max(0, min(pos, n - 1))
    return cluster[pos]


# --------------------------
# Trade generation (cluster-aware)
# --------------------------
def generate_trades_from_signals_clustered(df: pd.DataFrame,
                                           case: str = "average",
                                           cluster_gap_days: int = 3,
                                           avg_quantile: float = 0.5,
                                           greedy_quantile: float = 0.75) -> List[Dict[str, Any]]:
    """
    Create trades using clustered signals and case-specific quantiles.

    Returns list of trades (entry_price, exit_price, entry_date, exit_date).
    Algorithm:
      - cluster buy indices and sell indices separately
      - for each buy cluster in chronological order:
          - choose buy_idx according to case quantile (min->0.0, avg->0.5, greedy->0.75)
          - find the earliest sell cluster that starts after buy_idx date
          - choose sell_idx from that sell cluster with same quantile
          - create trade and skip buy clusters whose start date is before the sell date (no overlap)
    """
    trades: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return trades

    df = df.sort_values("date").reset_index(drop=True)
    if "buy_signal" not in df.columns or "sell_signal" not in df.columns:
        return trades

    buy_idxs = df.index[df["buy_signal"]].tolist()
    sell_idxs = df.index[df["sell_signal"]].tolist()
    if not buy_idxs:
        return trades

    buy_clusters = cluster_indices_by_date(df, buy_idxs, max_gap_days=cluster_gap_days)
    sell_clusters = cluster_indices_by_date(df, sell_idxs, max_gap_days=cluster_gap_days)

    # pick quantile for case
    if case == "min":
        q = 0.0
    elif case == "average":
        q = float(avg_quantile)
    elif case == "greedy":
        q = float(greedy_quantile)
    else:
        q = 0.5

    # iterate buy clusters and pair
    sell_cluster_ptr = 0
    for bcluster in buy_clusters:
        if not bcluster:
            continue
        buy_choice_idx = select_index_from_cluster(df, bcluster, quantile=q)
        buy_date = pd.to_datetime(df.loc[buy_choice_idx, "date"])
        entry_price = float(df.loc[buy_choice_idx, "close"])

        # find sell cluster that starts after buy_date
        matched_sell_idx = None
        matched_sell_cluster_idx = None
        for sc_i in range(sell_cluster_ptr, len(sell_clusters)):
            sc = sell_clusters[sc_i]
            if not sc:
                continue
            sc_start_idx = sc[0]
            sc_start_date = pd.to_datetime(df.loc[sc_start_idx, "date"])
            if sc_start_date > buy_date:
                # choose sell inside this cluster using same quantile
                sell_choice_idx = select_index_from_cluster(df, sc, quantile=q)
                matched_sell_idx = sell_choice_idx
                matched_sell_cluster_idx = sc_i
                break
        if matched_sell_idx is not None:
            exit_price = float(df.loc[matched_sell_idx, "close"])
            exit_date = pd.to_datetime(df.loc[matched_sell_idx, "date"])
            # advance sell_cluster_ptr to matched_sell_cluster_idx + 1 to avoid reusing earlier clusters
            sell_cluster_ptr = matched_sell_cluster_idx + 1
        else:
            # no sell after this buy cluster: exit at last available close in df_sub
            exit_price = float(df["close"].iloc[-1])
            exit_date = pd.to_datetime(df["date"].iloc[-1])
            # no more sells after this => future buys cannot be paired beyond end, but keep processing
            sell_cluster_ptr = len(sell_clusters)

        # Only create trade if exit_date > buy_date (or allow equal)
        trades.append({
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_date": buy_date.isoformat(),
            "exit_date": exit_date.isoformat()
        })

        # Move on — skip any buy clusters that start before exit_date to avoid overlap
        # Find next buy cluster with start date after exit_date
        # But since we're iterating, we will continue; so skip ahead in for-loop by checking
        # (implemented naturally as we process sequential clusters)

    return trades


# --------------------------
# Metrics & equity
# --------------------------
def compute_trade_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not trades:
        return {
            "num_trades": 0,
            "total_return_pct": 0.0,
            "win_rate": 0.0,
            "avg_return_per_trade": 0.0,
            "annualized_return_pct": None,
            "max_drawdown_pct": 0.0,
            "avg_holding_days": None
        }

    returns = []
    holding_days = []
    equity = [1.0]
    for t in trades:
        e = float(t["entry_price"])
        x = float(t["exit_price"])
        r = (x / e) - 1.0
        returns.append(r)
        equity.append(equity[-1] * (1.0 + r))
        ed = pd.to_datetime(t["entry_date"])
        xd = pd.to_datetime(t["exit_date"])
        holding_days.append((xd - ed).days if not pd.isna(xd) and not pd.isna(ed) else 0)

    total_return = equity[-1] - 1.0
    num_trades = len(returns)
    win_rate = float(sum(1 for r in returns if r > 0) / num_trades) if num_trades > 0 else 0.0
    avg_return = float(np.mean(returns)) if num_trades > 0 else 0.0
    avg_holding = float(np.mean(holding_days)) if holding_days else None

    try:
        start = pd.to_datetime(trades[0]["entry_date"])
        end = pd.to_datetime(trades[-1]["exit_date"])
        total_days = max(1, (end - start).days)
        annualized = (1.0 + total_return) ** (365.0 / total_days) - 1.0 if total_days > 0 else None
    except Exception:
        annualized = None

    eq = np.array(equity)
    peaks = np.maximum.accumulate(eq)
    drawdowns = (eq - peaks) / peaks
    max_dd = float(np.min(drawdowns)) if drawdowns.size > 0 else 0.0

    return {
        "num_trades": num_trades,
        "total_return_pct": float(total_return * 100.0),
        "win_rate": win_rate,
        "avg_return_per_trade": avg_return,
        "annualized_return_pct": float(annualized * 100.0) if annualized is not None else None,
        "max_drawdown_pct": float(max_dd * 100.0),
        "avg_holding_days": avg_holding
    }


def build_equity_curve_from_trades(trades: List[Dict[str, Any]], start_date=None, end_date=None) -> Tuple[List[str], List[float]]:
    """
    Step equity curve. Returns (iso-date-list, value-list).
    """
    if not trades:
        # return empty / flat series if date range provided
        if start_date is None or end_date is None:
            return [], []
        idx = pd.date_range(start=start_date, end=end_date, freq="D")
        return [d.isoformat() for d in idx], [1.0] * len(idx)

    trades_sorted = sorted(trades, key=lambda t: pd.to_datetime(t["exit_date"]))
    dates = []
    equity = []
    val = 1.0
    first_entry = pd.to_datetime(trades_sorted[0]["entry_date"])
    cur_date = pd.to_datetime(start_date) if start_date is not None else first_entry
    dates.append(pd.to_datetime(cur_date).isoformat())
    equity.append(val)

    for t in trades_sorted:
        ex_date = pd.to_datetime(t["exit_date"])
        prev_date = ex_date - pd.Timedelta(days=1)
        if pd.to_datetime(prev_date).isoformat() > dates[-1]:
            dates.append(pd.to_datetime(prev_date).isoformat())
            equity.append(val)
        r = (float(t["exit_price"]) / float(t["entry_price"])) - 1.0
        val = val * (1.0 + r)
        dates.append(ex_date.isoformat())
        equity.append(val)

    if end_date is not None:
        last_date = pd.to_datetime(end_date)
        if last_date.isoformat() > dates[-1]:
            dates.append(last_date.isoformat())
            equity.append(val)

    return dates, equity


# --------------------------
# Top-level evaluate wrapper
# --------------------------
def evaluate_strategy_for_timeframes(df: pd.DataFrame,
                                     timeframes: Dict[str, pd.Timestamp],
                                     params: Dict[str, Any] = None) -> Dict[str, Dict[str, Any]]:
    """
    Returns:
      results = {
        tf_name: {
          'min': {'trades': [...], 'metrics': {...}, 'equity': {'dates': [...], 'values': [...] }},
          'average': {...},
          'greedy': {...}
        }, ...
      }
    Params supports knobs:
      - bb_window, rsi_buy, rsi_sell, macd_hist_threshold, require_all
      - cluster_gap_days (int)
      - avg_quantile (float) default 0.5
      - greedy_quantile (float) default 0.75
    """
    if params is None:
        params = {}

    df = df.copy().sort_values("date").reset_index(drop=True)
    results: Dict[str, Dict[str, Any]] = {}

    for tf_name, start_ts in timeframes.items():
        start_ts = pd.to_datetime(start_ts)
        df_sub = df[df["date"] >= start_ts].copy().reset_index(drop=True)
        if df_sub.empty:
            results[tf_name] = {
                "min": {"trades": [], "metrics": compute_trade_metrics([]), "equity": {"dates": [], "values": []}},
                "average": {"trades": [], "metrics": compute_trade_metrics([]), "equity": {"dates": [], "values": []}},
                "greedy": {"trades": [], "metrics": compute_trade_metrics([]), "equity": {"dates": [], "values": []}}
            }
            continue

        # recompute signals based on knobs
        recomputed = recompute_signals(df_sub, params)

        cluster_gap_days = int(params.get("cluster_gap_days", 3))
        avg_q = float(params.get("avg_quantile", 0.5))
        greedy_q = float(params.get("greedy_quantile", 0.75))

        results[tf_name] = {}
        for case in ("min", "average", "greedy"):
            trades = generate_trades_from_signals_clustered(recomputed,
                                                            case=case,
                                                            cluster_gap_days=cluster_gap_days,
                                                            avg_quantile=avg_q,
                                                            greedy_quantile=greedy_q)
            metrics = compute_trade_metrics(trades)
            end_date = recomputed["date"].max() if not recomputed.empty else None
            dates, vals = build_equity_curve_from_trades(trades, start_date=start_ts, end_date=end_date)
            equity = {"dates": dates, "values": vals}
            results[tf_name][case] = {"trades": trades, "metrics": metrics, "equity": equity}

    return results
