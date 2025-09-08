# stock_tool/indicators.py
import pandas as pd
import numpy as np

def bollinger_bands(df: pd.DataFrame, window:int=20, n_std:float=2.0, price_col="close"):
    s = df[price_col].rolling(window=window, min_periods=1).mean()
    std = df[price_col].rolling(window=window, min_periods=1).std()
    upper = s + n_std * std
    lower = s - n_std * std
    out = pd.DataFrame({
        f"bb_sma_{window}": s,
        f"bb_upper_{window}": upper,
        f"bb_lower_{window}": lower
    }, index=df.index)
    return out

def rsi(df: pd.DataFrame, period:int=14, price_col="close"):
    delta = df[price_col].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing with ewm (alpha = 1/period)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(0)
    return pd.Series(rsi, name=f"rsi_{period}", index=df.index)

def macd(df: pd.DataFrame, price_col="close", fast=12, slow=26, signal=9):
    ema_fast = df[price_col].ewm(span=fast, adjust=False).mean()
    ema_slow = df[price_col].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    out = pd.DataFrame({
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_hist": hist
    }, index=df.index)
    return out

def add_all_indicators(df: pd.DataFrame, bb_window=20, rsi_period=14):
    """
    Return a DataFrame with original columns plus bb, rsi, macd
    """
    df2 = df.copy()
    bb = bollinger_bands(df2, window=bb_window)
    r = rsi(df2, period=rsi_period)
    m = macd(df2)
    merged = pd.concat([df2, bb, r, m], axis=1)
    return merged
