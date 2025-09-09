# etl/fetch_prices.py
import pandas as pd
import numpy as np
import yfinance as yf

DEFAULT_START = "2010-01-01"

def fetch_prices_and_indicators(tickers, start=DEFAULT_START):
    all_rows = []
    for t in tickers:
        t = t.strip().upper()
        try:
            tk = yf.Ticker(t)
            hist = tk.history(start=start, auto_adjust=False)
            if hist is None or hist.empty:
                print(f"[fetch_prices] no history for {t}")
                continue
            df = hist.reset_index().rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            # ensure date as YYYY-MM-DD
            df["date"] = pd.to_datetime(df["Date"] if "Date" in df.columns else df["date"]).dt.tz_localize(None).dt.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"[fetch_prices] failed ticker {t}: {e}")
            continue

        df["bb_sma_20"] = df["close"].rolling(window=20, min_periods=1).mean()
        df["bb_std_20"] = df["close"].rolling(window=20, min_periods=1).std().fillna(0)
        df["bb_upper_20"] = df["bb_sma_20"] + 2 * df["bb_std_20"]
        df["bb_lower_20"] = df["bb_sma_20"] - 2 * df["bb_std_20"]

        # RSI
        delta = df["close"].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        roll_up = up.rolling(14, min_periods=1).mean()
        roll_down = down.rolling(14, min_periods=1).mean().replace(0, np.nan)
        rs = roll_up / roll_down
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        df["buy_signal"] = ((df["rsi_14"] < 30) & (df["macd"] > df["macd_signal"])).astype(bool)
        df["sell_signal"] = ((df["rsi_14"] > 70) & (df["macd"] < df["macd_signal"])).astype(bool)

        out = df.reset_index(drop=True)
        out["ticker"] = t

        cols = ["ticker", "date", "open", "high", "low", "close", "volume",
                "bb_sma_20", "bb_upper_20", "bb_lower_20", "rsi_14",
                "macd", "macd_signal", "macd_hist", "buy_signal", "sell_signal"]
        for c in cols:
            if c not in out.columns:
                out[c] = np.nan
        out = out[cols]
        all_rows.append(out)

    if all_rows:
        return pd.concat(all_rows, ignore_index=True)
    else:
        return pd.DataFrame(columns=["ticker","date","open","high","low","close","volume",
                                     "bb_sma_20","bb_upper_20","bb_lower_20","rsi_14",
                                     "macd","macd_signal","macd_hist","buy_signal","sell_signal"])

if __name__ == "__main__":
    import os
    tickers = os.environ.get("TICKERS", "AAPL,MSFT").split(",")
    df = fetch_prices_and_indicators([t.strip() for t in tickers if t.strip()])
    print(df.head().to_dict(orient="records"))
