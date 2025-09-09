# etl/fetch_financials.py
import pandas as pd
import yfinance as yf
from .utils import to_json_text

def fetch_financials_all(tickers):
    """
    Returns DataFrame with financial rows.
    Columns: see fin_expected in run_all.py
    """
    rows = []
    for t in tickers:
        t = t.strip().upper()
        try:
            tk = yf.Ticker(t)
            fin = tk.financials    # income
            bal = tk.balance_sheet
            cf = tk.cashflow
        except Exception as e:
            print(f"[fetch_financials] failed ticker {t}: {e}")
            fin, bal, cf = None, None, None

        def df_period_dict(df):
            out = {}
            if df is None or df.empty:
                return out
            for col in df.columns:
                try:
                    period_key = pd.to_datetime(col).date().isoformat()
                except Exception:
                    period_key = str(col)
                s = df[col].to_dict()
                s = {k: (None if pd.isna(v) else v) for k, v in s.items()}
                out[period_key] = s
            return out

        fin_map = df_period_dict(fin)
        bal_map = df_period_dict(bal)
        cf_map = df_period_dict(cf)

        all_periods = sorted(set(list(fin_map.keys()) + list(bal_map.keys()) + list(cf_map.keys())))
        if not all_periods:
            info = getattr(tk, "info", {}) or {}
            mrq = info.get("mostRecentQuarter")
            if mrq:
                try:
                    all_periods = [pd.to_datetime(mrq).date().isoformat()]
                except Exception:
                    pass

        for p in all_periods:
            fin_r = fin_map.get(p, {})
            bal_r = bal_map.get(p, {})
            cf_r = cf_map.get(p, {})

            row = {
                "ticker": t,
                "period_end": p,
                "period_type": "FY",
                "reported_currency": None,
                "revenue": fin_r.get("Total Revenue") or fin_r.get("Revenue") or fin_r.get("totalRevenue"),
                "cost_of_revenue": fin_r.get("Cost of Revenue") or fin_r.get("CostOfRevenue"),
                "gross_profit": fin_r.get("Gross Profit") or fin_r.get("GrossProfit"),
                "operating_income": fin_r.get("Operating Income") or fin_r.get("OperatingIncome"),
                "net_income": fin_r.get("Net Income") or fin_r.get("NetIncome"),
                "eps_basic": fin_r.get("Basic EPS"),
                "eps_diluted": fin_r.get("Diluted EPS"),
                "ebitda": fin_r.get("EBITDA"),
                "gross_margin": fin_r.get("Gross Margin"),
                "operating_margin": fin_r.get("Operating Margin"),
                "ebitda_margin": fin_r.get("EBITDA Margin"),
                "net_profit_margin": fin_r.get("Net Profit Margin"),
                "total_assets": bal_r.get("Total Assets"),
                "total_liabilities": bal_r.get("Total Liab") or bal_r.get("totalLiabilities"),
                "total_equity": bal_r.get("Total Stockholder's Equity") or bal_r.get("Total stockholder equity"),
                "cash_and_equivalents": bal_r.get("Cash And Cash Equivalents") or bal_r.get("cashAndShortTermInvestments"),
                "total_debt": bal_r.get("Total Debt"),
                "operating_cashflow": cf_r.get("Total Cash From Operating Activities"),
                "capital_expenditures": cf_r.get("Capital Expenditures"),
                "free_cash_flow": None,
                "shares_outstanding": None,
                "shares_float": None,
                "market_cap": None,
                "price_to_earnings": None,
                "forward_pe": None,
                "peg_ratio": None,
                "revenue_growth": None,
                "earnings_growth": None,
                "number_of_analysts": None,
                "recommendation_mean": None,
                "fetched_at": pd.Timestamp.now().isoformat(),
                "raw_json": to_json_text({"income": fin_r, "balance": bal_r, "cashflow": cf_r})
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df

if __name__ == "__main__":
    import os
    tickers = os.environ.get("TICKERS", "AAPL,MSFT").split(",")
    df = fetch_financials_all([t.strip() for t in tickers if t.strip()])
    print(df.head().to_dict(orient="records"))
