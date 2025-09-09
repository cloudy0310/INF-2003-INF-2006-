# etl/fetch_companies.py
import pandas as pd
import yfinance as yf
from .utils import to_json_text

def fetch_companies_and_officers(tickers):
    """
    Returns: (companies_df, officers_df)
    companies_df columns: see comp_expected in run_all.py
    officers_df columns: ['ticker','name','title','year_of_birth','age','fiscal_year','total_pay','extra','created_at']
    """
    companies_rows = []
    officers_rows = []
    for t in tickers:
        t = t.strip().upper()
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
        except Exception as e:
            print(f"[fetch_companies] failed ticker {t}: {e}")
            info = {}

        row = {
            "ticker": t,
            "name": info.get("longName") or info.get("shortName"),
            "short_name": info.get("shortName"),
            "exchange": info.get("exchange"),
            "market": info.get("market"),
            "country": info.get("country"),
            "region": info.get("region"),
            "city": info.get("city"),
            "address1": info.get("address1"),
            "phone": info.get("phone"),
            "website": info.get("website"),
            "ir_website": info.get("irWebsite"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "industry_key": info.get("industryKey"),
            "long_business_summary": info.get("longBusinessSummary"),
            "full_time_employees": info.get("fullTimeEmployees"),
            "founded_year": info.get("founded"),
            "market_cap": info.get("marketCap"),
            "float_shares": info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "beta": info.get("beta"),
            "book_value": info.get("bookValue"),
            "dividend_rate": info.get("dividendRate"),
            "dividend_yield": info.get("dividendYield"),
            "last_dividend_date": None,
            "last_split_date": None,
            "last_split_factor": info.get("lastSplitFactor"),
            "logo_url": info.get("logo") or info.get("logo_url"),
            "esg_populated": info.get("esgPopulated"),
            "created_at": pd.Timestamp.now().isoformat(),
            "updated_at": pd.Timestamp.now().isoformat(),
            "raw_yfinance": to_json_text(info),
        }

        # yfinance sometimes returns epoch ints for dates
        if isinstance(info.get("lastDividendDate"), (int, float)):
            try:
                row["last_dividend_date"] = pd.to_datetime(info.get("lastDividendDate"), unit="s").date().isoformat()
            except Exception:
                row["last_dividend_date"] = None
        if isinstance(info.get("lastSplitDate"), (int, float)):
            try:
                row["last_split_date"] = pd.to_datetime(info.get("lastSplitDate"), unit="s").date().isoformat()
            except Exception:
                row["last_split_date"] = None

        companies_rows.append(row)

        officers = info.get("companyOfficers") or []
        for off in officers:
            officers_rows.append({
                "ticker": t,
                "name": off.get("name"),
                "title": off.get("title"),
                "year_of_birth": off.get("yearBorn"),
                "age": off.get("age"),
                "fiscal_year": off.get("fiscalYear"),
                "total_pay": off.get("totalPay"),
                "extra": to_json_text({k: off.get(k) for k in off.keys() if k not in ["name","title","yearBorn","age","fiscalYear","totalPay"]}),
                "created_at": pd.Timestamp.now().isoformat()
            })

    comp_df = pd.DataFrame(companies_rows)
    off_df = pd.DataFrame(officers_rows)
    return comp_df, off_df

if __name__ == "__main__":
    import os
    tickers = os.environ.get("TICKERS", "AAPL,MSFT").split(",")
    comp_df, off_df = fetch_companies_and_officers([t.strip() for t in tickers if t.strip()])
    print(comp_df.head().to_dict(orient="records"))
    print(off_df.head().to_dict(orient="records"))
