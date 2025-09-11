# app.py
import streamlit as st
from streamlit import rerun
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import functions.fetch_data as fetch_data
import functions.indicators as indicators
import functions.ratios as ratios_mod
from functions import watchlist as watchlist_mod
import datetime
import yfinance as yf


st.set_page_config(layout="wide", page_title="Stock Research Tool")

st.title("📈 Stock Research Tool (Streamlit + yfinance)")

# simple page navigation (Main / Watchlist)
page = st.sidebar.radio("Page", ["Main", "Watchlist"], index=0)

if page == "Watchlist":
    st.header("📋 Watchlist")

    # --- Add ticker form ---
    with st.form("add_watchlist_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([3,1,1])
        with col1:
            new_ticker = st.text_input("Add ticker (e.g. AAPL)", value="", placeholder="Enter ticker").strip().upper()
        with col2:
            new_amount = st.number_input("Amount (SGD / USD)", min_value=0.0, step=1.0, format="%.2f", value=0.0)
        with col3:
            submitted = st.form_submit_button("Add / Update")
        if submitted and new_ticker:
            # If user leaves amount as 0.0 but intends empty, treat 0 as meaningful.
            watchlist_mod.add_to_watchlist(new_ticker, amount=new_amount)
            st.success(f"Added / updated {new_ticker} in watchlist.")
            rerun()  # refresh to show new card immediately

    # Load watchlist and show count
    wl_df = watchlist_mod.load_watchlist()
    st.write(f"Watchlist items: {len(wl_df)}")

    if wl_df.empty:
        st.info("Your watchlist is empty. Add tickers above.")
    else:
        # Display a simple table first (compact view)
        st.dataframe(wl_df.assign(
            added_at=wl_df["added_at"].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M") if not wl_df["added_at"].isna().all() else wl_df["added_at"]
        ))

        st.markdown("---")
        st.subheader("Watchlist — Cards")

        # For each ticker create a small card with actions
        for _, row in wl_df.iterrows():
            ticker = row["ticker"]
            amount = row["amount"] if pd.notna(row["amount"]) else None
            added_at = row["added_at"]

            with st.container():
                c1, c2, c3 = st.columns([1, 3, 1])
                # left: small logo if available
                with c1:
                    try:
                        t_obj = yf.Ticker(ticker)
                        logo = t_obj.info.get("logo_url") or None
                    except Exception:
                        logo = None
                    if logo:
                        st.image(logo, width=64)
                    else:
                        st.markdown(f"**{ticker}**")

                # middle: info (name, latest price)
                with c2:
                    # try latest close price (use cached price CSV if available)
                    latest_price = None
                    try:
                        # try reading price CSV we already save in db/
                        price_csv = Path("db") / f"{ticker}_price.csv"
                        if price_csv.exists():
                            p_df = pd.read_csv(price_csv, index_col=0, parse_dates=True)
                            if not p_df.empty:
                                latest_price = p_df.iloc[-1].get("close")
                        if latest_price is None:
                            # fallback: quick yfinance history
                            hist = t_obj.history(period="5d", interval="1d")
                            if hist is not None and not hist.empty:
                                latest_price = hist["Close"].iloc[-1]
                    except Exception:
                        latest_price = None

                    # show textual info
                    try:
                        longname = t_obj.info.get("shortName") or t_obj.info.get("longName") or ""
                    except Exception:
                        longname = ""
                    st.markdown(f"**{ticker} — {longname}**")
                    if latest_price is not None:
                        st.write(f"Latest close: {latest_price:.2f}")
                    else:
                        st.write("Latest close: N/A")
                    if pd.notna(added_at):
                        # display added time (UTC)
                        try:
                            at_disp = pd.to_datetime(added_at).tz_convert("UTC").strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            try:
                                at_disp = str(added_at)
                            except Exception:
                                at_disp = ""
                        if at_disp:
                            st.caption(f"Added: {at_disp} UTC")

                # right: actions - delete & amount update
                with c3:
                    # Delete button
                    if st.button("Delete", key=f"del_{ticker}"):
                        watchlist_mod.remove_from_watchlist(ticker)
                        rerun()

                    # Update amount form
                    # We use a small form so the update is explicit
                    with st.form(f"amt_form_{ticker}", clear_on_submit=False):
                        new_amt_value = st.number_input(
                            "Amount",
                            min_value=0.0,
                            value=float(amount) if amount is not None else 0.0,
                            format="%.2f",
                            key=f"amt_input_{ticker}"
                        )
                        submitted_update = st.form_submit_button("Update")  # 🔹 removed key argument
                        if submitted_update:
                            watchlist_mod.update_amount(ticker, new_amt_value)
                            st.success(f"Updated amount for {ticker} to {new_amt_value:.2f}")
                            rerun()


    # stop further rendering of Main page under the Watchlist
    st.stop()


# --- Top input ---
col1, col2 = st.columns([3,1])
with col1:
    ticker_input = st.text_input("Enter stock ticker (e.g. AAPL, MSFT, TSLA)", value="AAPL").strip().upper()
with col2:
    fetch_button = st.button("Fetch / Refresh")

if not ticker_input:
    st.info("Type a ticker symbol above to get started.")
    st.stop()

# --- Fetch / cache wrapper ---
@st.cache_data(ttl=60*30)  # cache 30 minutes
def get_all_data(ticker: str, force_refresh: bool=False):
    # price history (fetch_price_history handles tail-append logic)
    hist = fetch_data.fetch_price_history(ticker, period="5y", interval="1d", force_refresh=force_refresh)
    # company info cached (max_age_days default 7)
    info = fetch_data.fetch_company_info_cached(ticker, force_refresh=force_refresh, max_age_days=7)
    # financial statements (no caching beyond yfinance object calls)
    fin_stmts = fetch_data.fetch_financial_statements(ticker)
    # compute indicators and save them
    df_ind = indicators.add_all_indicators(hist)
    fetch_data.save_indicators(ticker, df_ind, suffix="indicators")
    # company info saved by fetch_company_info_cached(), but to be safe we call save_company_info here as well
    try:
        fetch_data.save_company_info(ticker, info)
    except Exception:
        pass
    # news (defaults to 6 hours freshness)
    news_df = fetch_data.fetch_news_cached(ticker, force_refresh=force_refresh, max_age_hours=6)
    return {"history": hist, "indicators": df_ind, "info": info, "financials": fin_stmts, "news": news_df}

try:
    all_data = get_all_data(ticker_input, force_refresh=fetch_button)
except Exception as e:
    st.error(f"Error fetching data for {ticker_input}: {e}")
    st.stop()

hist = all_data["history"]
ind_df = all_data["indicators"]
info = all_data["info"]
financials = all_data["financials"]
news_df = all_data["news"]

# --- Ensure datetime indexes (FIX for your Index.date error) ---
# Convert hist and ind_df indexes to datetime safely and drop invalid rows if any.
try:
    hist.index = pd.to_datetime(hist.index, errors="coerce")
    hist = hist[~hist.index.isna()].sort_index()
except Exception:
    pass

try:
    ind_df.index = pd.to_datetime(ind_df.index, errors="coerce")
    ind_df = ind_df[~ind_df.index.isna()].sort_index()
except Exception:
    pass

# ensure raw price saved too
fetch_data.save_indicators(ticker_input, hist, suffix="price")

# --- Company info & ratios ---
st.header(f"{ticker_input} — Company info & key ratios")
col_a, col_b = st.columns([2,3])

with col_a:
    st.subheader("Profile")
    name = info.get("shortName") or info.get("longName") or ticker_input
    st.markdown(f"**{name}**")
    st.write(f"Sector: {info.get('sector','-')}  •  Industry: {info.get('industry','-')}")
    st.write(f"Market Cap: {info.get('marketCap', '-')}")    
    if info.get("logo_url"):
        st.image(info.get("logo_url"), width=120)

    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("Market Cap", f"{info.get('marketCap', 'N/A')}")
    mcol2.metric("Trailing P/E", f"{info.get('trailingPE', 'N/A')}")
    mcol3.metric("Forward P/E", f"{info.get('forwardPE', 'N/A')}")

    # show link to company CSV and allow download
    company_csv = Path("db") / f"{ticker_input}_company.csv"
    company_json = Path("db") / f"{ticker_input}_company.json"
    if company_csv.exists():
        with open(company_csv, "rb") as f:
            st.download_button("Download company CSV", data=f, file_name=company_csv.name)
    elif company_json.exists():
        with open(company_json, "rb") as f:
            st.download_button("Download company JSON", data=f, file_name=company_json.name)

with col_b:
    st.subheader("Computed key ratios (best-effort)")
    key_ratios = ratios_mod.compute_key_ratios(info, financials)
    kr_df = pd.DataFrame.from_dict(key_ratios, orient="index", columns=["value"])
    kr_df.index.name = "ratio"
    st.dataframe(kr_df)

# --- Chart controls & plotting ---
st.header("Interactive chart with indicators")
chart_col, table_col = st.columns([3,1])

with chart_col:
    # protect against empty hist/ind_df
    if hist.empty or ind_df.empty:
        st.warning("Price or indicator data is empty. Try clicking Fetch / Refresh.")
    else:
        min_date = hist.index.min().date()
        max_date = hist.index.max().date()
        default_start = max_date - datetime.timedelta(days=365)
        start_date, end_date = st.date_input("Select date range", value=(default_start, max_date),
                                             min_value=min_date, max_value=max_date)
        show_bb = st.checkbox("Show Bollinger Bands (20)", value=True)
        show_sma = st.checkbox("Show SMA 20", value=True)
        show_rsi = st.checkbox("Show RSI (14)", value=True)
        show_macd = st.checkbox("Show MACD", value=True)

        # ---------- DATE-ONLY COMPARISON (no timezone) ----------
        # Create a boolean mask by comparing the index dates with the selected start/end dates.
        # Use pd.Series(..., index=ind_df.index).between(...) so the mask is aligned with the DataFrame index.
        try:
            index_dates_series = pd.Series(ind_df.index.date, index=ind_df.index)
            mask = index_dates_series.between(start_date, end_date)
        except Exception:
            # Fallback: try numpy-style comparison (less aligned but usually works)
            mask = (ind_df.index.date >= start_date) & (ind_df.index.date <= end_date)

        plot_df = ind_df.loc[mask].copy()

        if plot_df.empty:
            st.warning("No data in selected date range.")
        else:
            rows = 1 + (1 if show_rsi else 0) + (1 if show_macd else 0)
            row_heights = [0.6] + ([0.2] * (rows - 1))
            fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                                vertical_spacing=0.03,
                                row_heights=row_heights)

            current_row = 1
            # Build hovertext list to be compatible across Plotly versions
            hover_texts = [
                f"{idx.strftime('%Y-%m-%d')}<br>Open: {o:.2f}<br>High: {h:.2f}<br>Low: {l:.2f}<br>Close: {c:.2f}"
                for idx, o, h, l, c in zip(plot_df.index, plot_df["open"], plot_df["high"], plot_df["low"], plot_df["close"])
            ]

            fig.add_trace(
                go.Candlestick(
                    x=plot_df.index,
                    open=plot_df["open"],
                    high=plot_df["high"],
                    low=plot_df["low"],
                    close=plot_df["close"],
                    name="Price",
                    increasing_line_color="green",
                    decreasing_line_color="red",
                    hovertext=hover_texts,
                    hoverinfo="x+text"
                ),
                row=current_row, col=1
            )

            if show_sma and f"bb_sma_20" in plot_df.columns:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["bb_sma_20"], mode="lines",
                                         name="SMA20", line=dict(width=1.5)), row=current_row, col=1)
            if show_bb and "bb_upper_20" in plot_df.columns and "bb_lower_20" in plot_df.columns:
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["bb_upper_20"], name="BB Upper", line=dict(width=1), opacity=0.6),
                              row=current_row, col=1)
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["bb_lower_20"], name="BB Lower", line=dict(width=1), opacity=0.6),
                              row=current_row, col=1)

            if show_rsi:
                current_row += 1
                rsi_col = f"rsi_14" if f"rsi_14" in plot_df.columns else [c for c in plot_df.columns if c.startswith("rsi_")][0]
                fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[rsi_col], name="RSI", mode="lines"), row=current_row, col=1)
                try:
                    fig.add_hline(y=70, line_dash="dash", row=current_row, col=1)
                    fig.add_hline(y=30, line_dash="dash", row=current_row, col=1)
                except Exception:
                    fig.add_trace(go.Scatter(x=[plot_df.index.min(), plot_df.index.max()], y=[70,70],
                                             mode="lines", showlegend=False, hoverinfo="skip"), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=[plot_df.index.min(), plot_df.index.max()], y=[30,30],
                                             mode="lines", showlegend=False, hoverinfo="skip"), row=current_row, col=1)

            if show_macd:
                current_row += 1
                if "macd" in plot_df.columns and "macd_signal" in plot_df.columns and "macd_hist" in plot_df.columns:
                    fig.add_trace(go.Bar(x=plot_df.index, y=plot_df["macd_hist"], name="MACD Hist"), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["macd"], name="MACD Line"), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["macd_signal"], name="MACD Signal"), row=current_row, col=1)

            fig.update_layout(height=800, showlegend=True, margin=dict(l=15, r=15, t=35, b=20))
            fig.update_xaxes(type="date")
            st.plotly_chart(fig, use_container_width=True)

with table_col:
    st.subheader("Latest data & CSV")
    if not hist.empty:
        latest = hist.iloc[-1]
        st.write("Latest close", latest["close"])
    else:
        st.write("No price data available.")
    st.write("Most recent indicator snapshot")
    st.dataframe(ind_df.tail(5))
    price_csv = Path("db") / f"{ticker_input}_price.csv"
    ind_csv = Path("db") / f"{ticker_input}_indicators.csv"
    if price_csv.exists():
        with open(price_csv, "rb") as f:
            st.download_button(label="Download price CSV", data=f, file_name=price_csv.name)
    if ind_csv.exists():
        with open(ind_csv, "rb") as f:
            st.download_button(label="Download indicators CSV", data=f, file_name=ind_csv.name)

# --- News Section ---
st.markdown("---")
st.header("News")
if news_df is None or news_df.empty:
    st.info("No recent news available or news fetch returned nothing.")
else:
    for idx, row in news_df.iterrows():
        title = row.get("title", "") or "No title"
        link = row.get("link", "")
        pub = row.get("publisher", "")
        dt = row.get("datetime", "")
        # datetime may be ISO string; show short date/time
        dt_display = ""
        if pd.notna(dt) and dt:
            try:
                dt_display = pd.to_datetime(dt).strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_display = str(dt)
        if link:
            st.markdown(f"- [{title}]({link}) — {pub}  `{dt_display}`")
        else:
            st.markdown(f"- {title} — {pub}  `{dt_display}`")

    news_csv = Path("db") / f"{ticker_input}_news.csv"
    if news_csv.exists():
        with open(news_csv, "rb") as f:
            st.download_button("Download news CSV", data=f, file_name=news_csv.name)

st.markdown("---")
st.caption("Company info and news are cached to the db/ folder. News freshness defaults to 6 hours; company info to 7 days. You can force a refresh with the 'Fetch / Refresh' button.")
