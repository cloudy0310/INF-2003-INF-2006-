import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from api.stock_analysis import get_company_info, get_financials, get_stock_prices
from api.stock_analysis_helper import evaluate_strategy_for_timeframes
from api.watchlist import get_or_create_default_watchlist, upsert_watchlist_item
import os

def _ensure_local_watchlist():
    if "local_watchlist" not in st.session_state:
        st.session_state.local_watchlist = set()

def page(supabase=None):
    st.title("📈 Stock Analysis Dashboard")
    st.caption("Demo mode: login removed. Watchlist is stored locally in this browser session.")

    _ensure_local_watchlist()

    ticker = st.text_input("Search Stock Ticker (e.g., AAPL, MSFT)").upper().strip()
    if not ticker:
        st.info("Enter a ticker symbol to start analysis.")
        st.stop()

    st.subheader("🏢 Company Overview")
    try:
        company_info = get_company_info(ticker)
    except Exception as e:
        company_info = None
        st.error(f"Failed to fetch company info: {e}")

    if company_info:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**Name:** {company_info.get('name', 'N/A')}")
            st.markdown(f"**Ticker:** {company_info.get('ticker', 'N/A')}")
            st.markdown(f"**Sector:** {company_info.get('sector', 'N/A')}")
        with col2:
            st.markdown(f"**Industry:** {company_info.get('industry', 'N/A')}")
            st.markdown(f"**Headquarters:** {company_info.get('headquarters', 'N/A')}")
            st.markdown(f"**CEO:** {company_info.get('ceo', 'N/A')}")
        with col3:
            st.markdown(f"**Founded:** {company_info.get('founded', 'N/A')}")
            st.markdown(f"**Employees:** {company_info.get('employees', 'N/A')}")
            st.markdown(f"**Website:** {company_info.get('website', 'N/A')}")
    else:
        st.warning("No company info found.")

    st.subheader("💰 Key Financials")
    try:
        df_fin = get_financials(ticker)
    except Exception as e:
        st.error(f"Failed to fetch financials: {e}")
        df_fin = pd.DataFrame()

    if not df_fin.empty:
        df_fin = df_fin.rename(columns={
            'fiscal_year': 'Year',
            'revenue': 'Revenue ($M)',
            'net_income': 'Net Income ($M)',
            'eps': 'EPS',
            'ebitda': 'EBITDA ($M)'
        })
        st.write(df_fin.style.format({
            'Revenue ($M)': "${:,.0f}",
            'Net Income ($M)': "${:,.0f}",
            'EPS': "{:.2f}",
            'EBITDA ($M)': "${:,.0f}"
        }))
    else:
        st.warning("No financial data found.")

    st.subheader("📊 Stock Price History")
    try:
        df_price = get_stock_prices(ticker)
    except Exception as e:
        st.error(f"Failed to load stock prices: {e}")
        st.stop()

    if df_price.empty:
        st.warning("No stock price data found.")
        st.stop()

    df_price['date'] = pd.to_datetime(df_price['date'], errors='coerce')
    if df_price['date'].isna().any():
        st.warning("Found invalid date values in data. Dropping invalid rows.")
        df_price = df_price.dropna(subset=['date'])

    numeric_cols = ['open', 'high', 'low', 'close', 'bb_sma_20', 'bb_upper_20', 'bb_lower_20',
                    'rsi_14', 'macd', 'macd_signal', 'macd_hist', 'volume']
    for col in numeric_cols:
        if col in df_price.columns:
            df_price[col] = pd.to_numeric(df_price[col], errors='coerce')
    if all(c in df_price.columns for c in ['open', 'high', 'low', 'close']):
        df_price = df_price.dropna(subset=['open', 'high', 'low', 'close'])

    for sig in ('buy_signal', 'sell_signal'):
        if sig in df_price.columns:
            df_price[sig] = df_price[sig].astype(bool)
        else:
            df_price[sig] = False

    df_price = df_price.sort_values('date').reset_index(drop=True)

    if st.checkbox("Show debug info (dates/rows)"):
        st.write("dtype:", df_price['date'].dtype)
        st.write("min date:", df_price['date'].min())
        st.write("max date:", df_price['date'].max())
        st.write("rows:", len(df_price))
        st.write("Newest rows (desc):")
        st.write(df_price.sort_values('date', ascending=False).head(10))
        if 'year' not in df_price.columns:
            df_price['year'] = df_price['date'].dt.year
        st.write(df_price['year'].value_counts().sort_index().to_frame("count"))

    latest_date = df_price['date'].max()
    date_ranges = {
        "3M": latest_date - pd.DateOffset(months=3),
        "6M": latest_date - pd.DateOffset(months=6),
        "YTD": pd.Timestamp(datetime(latest_date.year, 1, 1)),
        "1Y": latest_date - pd.DateOffset(years=1),
        "3Y": latest_date - pd.DateOffset(years=3),
        "5Y": latest_date - pd.DateOffset(years=5),
        "10Y": latest_date - pd.DateOffset(years=10),
        "All": df_price['date'].min()
    }
    options = list(date_ranges.keys())
    default_index = options.index("1Y") if "1Y" in options else 0
    selected_range = st.radio("Select Time Range:", options=options, index=default_index, horizontal=True)
    start_date = date_ranges[selected_range]
    df_plot = df_price[df_price['date'] >= start_date].copy()
    if df_plot.empty:
        st.warning("No data for selected date range.")
        st.stop()

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.6,0.2,0.2])
    fig.add_trace(go.Candlestick(
        x=df_plot['date'], open=df_plot['open'], high=df_plot['high'],
        low=df_plot['low'], close=df_plot['close'], name='Price',
        increasing_line_color='rgba(0,200,0,1)', decreasing_line_color='rgba(200,0,0,1)', showlegend=False
    ), row=1, col=1)

    if all(c in df_plot.columns for c in ['bb_upper_20','bb_lower_20','bb_sma_20']):
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['bb_upper_20'], line=dict(width=1), name='BB Upper', hoverinfo='skip', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['bb_lower_20'], line=dict(width=1), name='BB Lower', hoverinfo='skip', showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['bb_sma_20'], line=dict(width=1, dash='dot'), name='BB SMA', hoverinfo='skip', showlegend=False), row=1, col=1)

    if 'buy_signal' in df_plot.columns and 'sell_signal' in df_plot.columns:
        buys = df_plot[df_plot['buy_signal']]
        sells = df_plot[df_plot['sell_signal']]
        buy_marker = dict(symbol='triangle-up', size=16, color='green', line=dict(color='darkgreen', width=2))
        sell_marker = dict(symbol='triangle-down', size=16, color='red', line=dict(color='darkred', width=2))
        if not buys.empty:
            fig.add_trace(go.Scatter(x=buys['date'], y=buys['close'], mode='markers', marker=buy_marker, name='Buy Signal',
                                     hovertemplate='Buy<br>%{x|%Y-%m-%d}<br>Price: %{y:.2f}<extra></extra>'), row=1, col=1)
        if not sells.empty:
            fig.add_trace(go.Scatter(x=sells['date'], y=sells['close'], mode='markers', marker=sell_marker, name='Sell Signal',
                                     hovertemplate='Sell<br>%{x|%Y-%m-%d}<br>Price: %{y:.2f}<extra></extra>'), row=1, col=1)

    if 'macd' in df_plot.columns and 'macd_signal' in df_plot.columns:
        fig.add_trace(go.Bar(x=df_plot['date'], y=df_plot.get('macd_hist', pd.Series([0]*len(df_plot))), name='MACD Hist', marker=dict(), showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['macd'], name='MACD', line=dict(width=1.5), showlegend=False), row=2, col=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['macd_signal'], name='Signal', line=dict(width=1, dash='dot'), showlegend=False), row=2, col=1)

    if 'rsi_14' in df_plot.columns:
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi_14'], name='RSI', line=dict(width=1.2), showlegend=False), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="lightgrey", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="lightgrey", row=3, col=1)

    fig.update_layout(dragmode='pan', height=720, margin=dict(l=20, r=20, t=40, b=20),
                      xaxis=dict(rangeslider=dict(visible=False)))
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="MACD", row=2, col=1)
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])
    st.plotly_chart(fig, use_container_width=True, config={"modeBarButtonsToAdd": ["pan2d"], "displaylogo": False, "scrollZoom": True})

    # Trading Analysis
    st.markdown("---")
    st.subheader("⚖️ Trading Analysis — Mean Reversion Strategy")

    with st.expander("What is this? (Mean Reversion strategy explanation)"):
        st.write("Recompute indicators and signals using knobs, then compute cluster-based trades for min/average/greedy cases.")
        st.markdown("- Buy: price < BB_lower AND RSI < RSI_buy AND MACD_hist crossing up.")
        st.markdown("- Sell: price > BB_upper OR RSI > RSI_sell OR MACD_hist < threshold.")

    with st.expander("Quick strategy knobs (these recompute signals)"):
        rsi_buy_thresh = st.number_input("RSI buy threshold", value=35, step=1)
        rsi_sell_thresh = st.number_input("RSI sell threshold", value=70, step=1)
        bb_window = st.number_input("Bollinger window", value=20, step=1)
        macd_hist_threshold = st.number_input("MACD hist threshold (for buy cross)", value=0.0, step=0.1)
        require_all = st.checkbox("Require all conditions for BUY", value=True)
        cluster_gap_days = st.number_input("Cluster gap days", value=3, step=1)
        avg_quantile = st.slider("Average quantile (median)", min_value=0.0, max_value=1.0, value=0.5, step=0.05)
        greedy_quantile = st.slider("Greedy quantile (late)", min_value=0.0, max_value=1.0, value=0.75, step=0.05)

    st.markdown("**Case definitions:**")
    st.markdown("- **Min:** earliest in buy cluster; pair with earliest subsequent sell cluster.")
    st.markdown("- **Average:** center of buy cluster (median); pair with median of next sell cluster.")
    st.markdown("- **Greedy:** late in buy cluster (75th percentile); pair with late sell.")

    tf_options = ["YTD", "1Y", "3Y", "5Y", "10Y"]
    selected_tfs = st.multiselect("Select timeframes to evaluate", options=tf_options, default=["YTD", "1Y", "3Y"])

    latest_date = df_price['date'].max()
    timeframe_map = {}
    for tf in selected_tfs:
        if tf == "YTD":
            timeframe_map[tf] = pd.Timestamp(datetime(latest_date.year, 1, 1))
        elif tf == "1Y":
            timeframe_map[tf] = latest_date - pd.DateOffset(years=1)
        elif tf == "3Y":
            timeframe_map[tf] = latest_date - pd.DateOffset(years=3)
        elif tf == "5Y":
            timeframe_map[tf] = latest_date - pd.DateOffset(years=5)
        elif tf == "10Y":
            timeframe_map[tf] = latest_date - pd.DateOffset(years=10)

    if st.button("Run trading analysis"):
        if not selected_tfs:
            st.warning("Please select at least one timeframe.")
        else:
            with st.spinner("Computing trading performance..."):
                params = {
                    "rsi_buy": rsi_buy_thresh,
                    "rsi_sell": rsi_sell_thresh,
                    "bb_window": bb_window,
                    "macd_hist_threshold": macd_hist_threshold,
                    "require_all": require_all,
                    "cluster_gap_days": cluster_gap_days,
                    "avg_quantile": avg_quantile,
                    "greedy_quantile": greedy_quantile
                }
                try:
                    results = evaluate_strategy_for_timeframes(df_price, timeframe_map, params=params)
                except Exception as e:
                    st.error(f"Failed to evaluate strategy: {e}")
                    results = {}

            st.subheader("Performance snapshots")
            for tf in selected_tfs:
                st.markdown(f"### {tf}")
                cols = st.columns([1,1,1])
                cases = ["min", "average", "greedy"]
                for col, case in zip(cols, cases):
                    with col:
                        tf_res = results.get(tf, {}).get(case, {})
                        metrics = tf_res.get("metrics", {})
                        if not metrics or metrics.get("num_trades",0) == 0:
                            st.markdown(f"#### {case.title()}")
                            st.info("No trades")
                        else:
                            st.markdown(f"#### {case.title()}")
                            st.metric(label="Total Return", value=f"{metrics['total_return_pct']:.2f}%")
                            st.write(f"Trades: **{metrics['num_trades']}** • Win: **{metrics['win_rate']*100:.0f}%**")
                            if metrics.get("annualized_return_pct") is not None:
                                st.write(f"Ann: **{metrics['annualized_return_pct']:.2f}%**")
                            st.write(f"Avg/trade: **{metrics['avg_return_per_trade']*100:.2f}%**")
                            avg_h = metrics.get("avg_holding_days")
                            st.write(f"Holding (days): **{avg_h:.1f}**" if avg_h is not None else "Holding (days): N/A")
                            st.write(f"Max DD: **{metrics['max_drawdown_pct']:.2f}%**")

            st.subheader("Detailed results (per timeframe & case)")
            for tf in selected_tfs:
                st.markdown(f"### {tf}")
                tf_results = results.get(tf, {})
                cols = st.columns(3)
                cases = ["min", "average", "greedy"]
                for col, case in zip(cols, cases):
                    with col:
                        case_res = tf_results.get(case, {})
                        metrics = case_res.get("metrics", {})
                        trades = case_res.get("trades", [])
                        st.markdown(f"**{case.title()} case**")
                        if not trades:
                            st.info("No trades")
                            continue
                        st.metric(label="Total Return", value=f"{metrics['total_return_pct']:.2f}%")
                        st.write(f"Trades: **{metrics['num_trades']}** • Win: **{metrics['win_rate']*100:.0f}%**")
                        if metrics.get("annualized_return_pct") is not None:
                            st.write(f"Ann: **{metrics['annualized_return_pct']:.2f}%**")
                        st.write(f"Avg/trade: **{metrics['avg_return_per_trade']*100:.2f}%**")
                        avg_h = metrics.get("avg_holding_days")
                        st.write(f"Holding (days): **{avg_h:.1f}**" if avg_h is not None else "Holding (days): N/A")
                        st.write(f"Max DD: **{metrics['max_drawdown_pct']:.2f}%**")
                        try:
                            df_tr = pd.DataFrame(trades)
                            if not df_tr.empty:
                                df_tr["entry_date"] = pd.to_datetime(df_tr["entry_date"])
                                df_tr["exit_date"] = pd.to_datetime(df_tr["exit_date"])
                                df_tr["return_pct"] = ((df_tr["exit_price"] / df_tr["entry_price"]) - 1.0) * 100.0
                                df_tr = df_tr[["entry_date", "exit_date", "entry_price", "exit_price", "return_pct"]]
                                df_tr = df_tr.rename(columns={
                                    "entry_date": "Entry Date",
                                    "exit_date": "Exit Date",
                                    "entry_price": "Entry Price",
                                    "exit_price": "Exit Price",
                                    "return_pct": "Return (%)"
                                })
                                st.dataframe(df_tr.style.format({
                                    "Entry Price": "{:.2f}",
                                    "Exit Price": "{:.2f}",
                                    "Return (%)": "{:.2f}"
                                }), height=220)
                        except Exception as e:
                            st.write("Unable to render trade table:", e)

            st.subheader("Cumulative equity curves (per case)")
            for case in ("min", "average", "greedy"):
                fig_eq = go.Figure()
                any_series = False
                for tf in selected_tfs:
                    equity = results.get(tf, {}).get(case, {}).get("equity", {})
                    dates = equity.get("dates", [])
                    values = equity.get("values", [])
                    if dates and values:
                        any_series = True
                        fig_eq.add_trace(go.Scatter(
                            x=[pd.to_datetime(d) for d in dates], y=values,
                            mode="lines+markers", name=tf,
                            hovertemplate="%{x|%Y-%m-%d}<br>Equity: %{y:.4f}<extra></extra>"
                        ))
                if any_series:
                    fig_eq.update_layout(title=f"{case.title()} case — Cumulative equity",
                                         height=320, margin=dict(l=20, r=20, t=30, b=10))
                    st.plotly_chart(fig_eq, use_container_width=True)
                else:
                    st.info(f"No equity data for {case} case to plot.")

    # -------------------- Add to watchlist --------------------
    st.markdown("---")
    st.subheader("Add to watchlist")

    FIXED_USER_ID = os.getenv("WATCHLIST_USER_ID")

    if st.button("➕ Add to watchlist"):
        try:
            wl = get_or_create_default_watchlist(supabase, FIXED_USER_ID)
            upsert_watchlist_item(supabase, wl["watchlist_id"], ticker, 0.0) 
            st.success(f"Added {ticker} to your watchlist with allocation 0.")
        except Exception as e:
            st.error(f"Failed to add {ticker} to watchlist: {e}")

