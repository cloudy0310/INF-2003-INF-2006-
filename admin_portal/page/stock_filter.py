# admin_portal/page/stock_filter.py
from __future__ import annotations

from typing import Optional
import streamlit as st
import pandas as pd
from supabase import Client
from datetime import date as dt_date, timedelta

# ==============================================================================
# Helper: Fetch Universe (Future-Proofed)
# ==============================================================================
@st.cache_data(ttl=300)
def fetch_stock_universe(_supabase: Client):
    try:
        # 1. Fetch ALL Companies
        comp_res = _supabase.table("companies").select("*").execute()
        df_companies = pd.DataFrame(comp_res.data)

        if df_companies.empty:
            return pd.DataFrame()

        # 2. Fetch Latest Metrics (Looking forward and backward)
        today = dt_date.today()
        start_d = today - timedelta(days=3650) 
        future_d = today + timedelta(days=1825) 
        
        metrics_res = (
            _supabase.table("stock_prices")
            .select("ticker, market_cap, pe_ratio, close, date")
            .gte("date", start_d.isoformat())
            .lte("date", future_d.isoformat()) 
            .order("date", desc=True)
            .execute()
        )
        df_prices = pd.DataFrame(metrics_res.data)

        # 3. Process: Keep ONLY the single latest row per ticker
        if not df_prices.empty:
            df_prices["date"] = pd.to_datetime(df_prices["date"])
            df_latest = df_prices.sort_values("date", ascending=False).drop_duplicates(subset=["ticker"])
            df_latest = df_latest.rename(columns={"date": "latest_record_date"})
        else:
            df_latest = pd.DataFrame()

        # 4. Merge
        if df_latest.empty:
            master_df = df_companies
        else:
            master_df = pd.merge(df_companies, df_latest, on="ticker", how="left")
        
        # Numeric cleanup
        for col in ["market_cap", "pe_ratio", "close"]:
            if col in master_df.columns:
                master_df[col] = pd.to_numeric(master_df[col], errors="coerce")
                
        return master_df

    except Exception as e:
        st.error(f"Error building stock universe: {e}")
        return pd.DataFrame()

def fetch_officers(_supabase: Client, ticker: str):
    try:
        res = (
            _supabase.table("company_officers")
            .select("*")
            .eq("ticker", ticker)
            .execute()
        )
        return pd.DataFrame(res.data)
    except Exception:
        return pd.DataFrame()

# ==============================================================================
# Main Page
# ==============================================================================
def page(supabase: Optional[Client] = None):
    if supabase is None:
        st.error("Supabase client missing.")
        st.stop()

    st.title("📊 Stock Filter")

    # ---- 1. Load Data ----
    with st.spinner("Analyzing market data..."):
        universe_df = fetch_stock_universe(supabase)

    if universe_df.empty:
        st.warning("No companies found.")
        st.stop()

    # =========================================================================
    # ---- 2. Sidebar: Filters (Sector & Price) ----
    # =========================================================================
    st.sidebar.header("1. Filter Companies")

    filtered_df = universe_df.copy()

    # --- A. Sector Filter ---
    sector_col = None
    if "sector" in universe_df.columns:
        sector_col = "sector"
    elif "industry" in universe_df.columns:
        sector_col = "industry"

    if sector_col:
        all_sectors = sorted(universe_df[sector_col].dropna().unique().tolist())
        selected_sectors = st.sidebar.multiselect("Sector", options=all_sectors, default=all_sectors)
        if selected_sectors:
            filtered_df = filtered_df[filtered_df[sector_col].isin(selected_sectors)]
    else:
        st.sidebar.caption("No sector column found.")

    # --- B. Price Filter (New!) ---
    st.sidebar.subheader("Price Range")
    
    # Defaults
    min_val = 0.0
    max_val = 10000.0 # Arbitrary high default
    
    # Smart defaults based on data if available
    if "close" in universe_df.columns:
        valid_prices = universe_df["close"].dropna()
        if not valid_prices.empty:
            max_val = float(valid_prices.max()) + 10.0
            
    c1, c2 = st.sidebar.columns(2)
    min_price = c1.number_input("Min ($)", min_value=0.0, value=0.0, step=10.0)
    max_price = c2.number_input("Max ($)", min_value=0.0, value=max_val, step=10.0)

    # Apply Price Filter (Only if close price exists)
    if "close" in filtered_df.columns:
        
        filtered_df = filtered_df[
            (filtered_df["close"] >= min_price) & 
            (filtered_df["close"] <= max_price) | 
            filtered_df["close"].isna()
        ]

    # =========================================================================
    # ---- 3. Sidebar: Select Ticker ----
    # =========================================================================
    st.sidebar.markdown("---")
    st.sidebar.header("2. Select Stock")
    
    available_tickers = sorted(filtered_df["ticker"].astype(str).unique().tolist())
    
    if not available_tickers:
        st.error("No companies match your filters.")
        st.stop()
        
    selected_ticker = st.sidebar.selectbox(f"Companies ({len(available_tickers)})", available_tickers)
    
    # Get metadata from the Universe (Snapshot)
    company_meta = filtered_df[filtered_df["ticker"] == selected_ticker].iloc[0]

    # =========================================================================
    # ---- 4. Sidebar: Date Range ----
    # =========================================================================
    st.sidebar.markdown("---")
    
    default_end = dt_date.today()
    default_start = default_end - timedelta(days=365)
    max_d = dt_date.today() + timedelta(days=1825)
    
    date_range = st.sidebar.date_input("Chart Date Range", value=(default_start, default_end), max_value=max_d)

    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d = date_range[0] if isinstance(date_range, (list, tuple)) else date_range
        end_d = max_d

    # =========================================================================
    # ---- 5. Fetch History ----
    # =========================================================================
    try:
        hist_res = (
            supabase
            .table("stock_prices")
            .select("*")
            .eq("ticker", selected_ticker)
            .gte("date", start_d.isoformat())
            .lte("date", end_d.isoformat())
            .order("date", desc=True)
            .execute()
        )
        hist_df = pd.DataFrame(hist_res.data)
        
        # Numeric conversions
        if not hist_df.empty:
            cols = ["close", "market_cap", "pe_ratio"]
            for c in cols:
                if c in hist_df.columns:
                    hist_df[c] = pd.to_numeric(hist_df[c], errors="coerce")
            hist_df["date"] = pd.to_datetime(hist_df["date"])

    except Exception as e:
        st.error(f"Failed to load history: {e}")
        st.stop()

    # =========================================================================
    # ---- 6. Dashboard (SMART METRICS) ----
    # =========================================================================
    st.subheader(f"{selected_ticker} - {company_meta.get('name', '')}")

    # --- LOGIC: PREFER HISTORY DATA ---
    display_price = company_meta.get("close")
    display_mc = company_meta.get("market_cap")
    display_pe = company_meta.get("pe_ratio")

    if not hist_df.empty:
        # Sort history by date to find the absolute latest row in the loaded data
        latest_row = hist_df.sort_values("date").iloc[-1]
        
        # Override Price
        if pd.notna(latest_row.get("close")):
            display_price = latest_row["close"]
        # Override Market Cap
        if pd.notna(latest_row.get("market_cap")):
            display_mc = latest_row["market_cap"]
        # Override P/E
        if pd.notna(latest_row.get("pe_ratio")):
            display_pe = latest_row["pe_ratio"]

    # ---- METRICS ROW ----
    m1, m2, m3, m4 = st.columns(4)
    
    # 1. Price
    if pd.notna(display_price):
        m1.metric("Last Price", f"${display_price:,.2f}")
    else:
        m1.metric("Last Price", "N/A")

    # 2. Market Cap
    if pd.notna(display_mc):
        m2.metric("Market Cap", f"{display_mc:,.2f} M")
    else:
        m2.metric("Market Cap", "N/A")

    # 3. P/E Ratio
    if pd.notna(display_pe):
        m3.metric("P/E Ratio", f"{display_pe:.2f}")
    else:
        m3.metric("P/E Ratio", "N/A")

    # 4. Sector
    sec_val = company_meta.get(sector_col) if sector_col else "N/A"
    m4.metric("Sector", sec_val if pd.notna(sec_val) else "N/A")

    st.divider()

    tab_chart, tab_officers, tab_data = st.tabs(["📈 Price Chart", "👔 Company Officers", "💾 Raw Data"])

    # --- Chart ---
    with tab_chart:
        if not hist_df.empty:
            chart_data = hist_df.sort_values("date")
            st.line_chart(chart_data.set_index("date")["close"], use_container_width=True)
        else:
            st.info("No price history found.")

    # --- Officers ---
    with tab_officers:
        officers_df = fetch_officers(supabase, selected_ticker)
        if not officers_df.empty:
            if "total_pay" in officers_df.columns:
                officers_df["total_pay"] = pd.to_numeric(officers_df["total_pay"], errors="coerce")
                officers_df["Formatted Pay"] = officers_df["total_pay"].apply(
                    lambda x: f"${x:,.0f}" if pd.notna(x) else ""
                )
            
            cols_to_show = ["name", "title", "year_of_birth", "Formatted Pay"]
            final_cols = [c for c in cols_to_show if c in officers_df.columns]
            
            st.dataframe(officers_df[final_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No officer data available.")

    # --- Data ---
    with tab_data:
        st.dataframe(hist_df, use_container_width=True)