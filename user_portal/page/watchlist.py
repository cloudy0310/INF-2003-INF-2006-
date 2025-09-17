# user_page/watchlist.py
from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from supabase import Client
from api.watchlist import (
    get_or_create_default_watchlist,
    list_watchlist_items,
    upsert_watchlist_item,
    delete_watchlist_item,
    update_watchlist_item,
)
from api.portfolio import compute_portfolio_history

FIXED_USER_ID = os.getenv("WATCHLIST_USER_ID") or "24743632-db93-4f83-bf63-6f995cb6a6d6"

def _tip_label(text: str, tip: str) -> str:
    # hover tooltip via HTML title=""
    return f"{text} <span style='color:#9aa0a6' title='{tip}'>ℹ️</span>"

def page(supabase: Client = None):
    if supabase is None:
        st.error("Supabase client missing: router must call admin_page(supabase=supabase).")
        st.stop()

    st.title("🔖 Watchlist Manager")
    st.caption(f"User: `{FIXED_USER_ID}`")

    # ensure single watchlist exists
    try:
        wl = get_or_create_default_watchlist(supabase, FIXED_USER_ID)
    except Exception as e:
        st.error(f"Failed to get/create watchlist: {e}")
        st.stop()
    wid = wl["watchlist_id"]

    # ---------- Add / Update (top) ----------
    st.subheader("Add / Update a stock")
    a1, a2, a3 = st.columns([1.4, 1.2, 0.8])
    with a1:
        add_ticker = st.text_input("New ticker", key="add_tkr", placeholder="e.g., AAPL").upper().strip()
    with a2:
        add_alloc = st.number_input("Allocation (absolute)", key="add_alloc", min_value=0.0, step=1.0, value=0.0)
    with a3:
        if st.button("➕ Add / Upsert", key="add_btn"):
            if not add_ticker:
                st.warning("Please enter a ticker.")
            else:
                try:
                    upsert_watchlist_item(supabase, wid, add_ticker, float(add_alloc))
                    st.success(f"{add_ticker} added/updated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add/update {add_ticker}: {e}")

    st.divider()

    # ---------- Existing items ----------
    try:
        items, name_map = list_watchlist_items(supabase, wid)
    except Exception as e:
        st.error(f"Failed to load items: {e}")
        items, name_map = [], {}
    st.subheader("Your watchlist")

    # Header
    h1, h2, h3 = st.columns([1.4, 1.2, 0.8])
    h1.markdown("**Ticker**")
    h2.markdown("**Allocation (absolute)**")
    h3.markdown("**Delete**")

    pending_changes = []

    if not items:
        st.info("No stocks yet. Use the form above to add your first ticker.")
    else:
        for row in items:
            orig_ticker = row["ticker"]
            company = name_map.get(orig_ticker, "")
            t_key = f"ed_ticker_{wid}_{orig_ticker}"
            a_key = f"ed_alloc_{wid}_{orig_ticker}"
            d_key = f"del_{wid}_{orig_ticker}"

            c1, c2, c3 = st.columns([1.4, 1.2, 0.8])
            with c1:
                new_ticker = st.text_input("Ticker", key=t_key, value=orig_ticker)
                if company:
                    st.caption(company)
            with c2:
                new_alloc = st.number_input(
                    "Allocation",
                    key=a_key,
                    value=float(row.get("allocation") or 0.0),
                    step=1.0,
                    min_value=0.0
                )
            with c3:
                if st.button("🗑️ Delete", key=d_key):
                    try:
                        delete_watchlist_item(supabase, wid, orig_ticker)
                        st.success(f"Deleted {orig_ticker}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete {orig_ticker}: {e}")

            changed = (
                new_ticker.strip().upper() != orig_ticker.strip().upper()
                or float(new_alloc or 0.0) != float(row.get("allocation") or 0.0)
            )
            if changed:
                c1.caption("**∗ unsaved**")
                pending_changes.append({
                    "old_ticker": orig_ticker,
                    "new_ticker": new_ticker,
                    "allocation": float(new_alloc or 0.0),
                })

    # Save all
    if pending_changes:
        st.warning(f"{len(pending_changes)} row(s) have unsaved changes.")
        if st.button("💾 Save All Changes", use_container_width=True):
            errors = []
            for ch in pending_changes:
                try:
                    update_watchlist_item(supabase, wid, ch["old_ticker"], ch["new_ticker"], ch["allocation"])
                except Exception as e:
                    errors.append(f"{ch['old_ticker']} → {ch['new_ticker']}: {e}")
            if errors:
                st.error("Some rows failed to save:\n- " + "\n- ".join(errors))
            else:
                st.success("All changes saved.")
                st.rerun()
    else:
        st.info("No unsaved changes.")

    st.divider()

    # ---------- 📊 Portfolio analysis ----------
    st.subheader("📊 Portfolio analysis")

    today = pd.Timestamp.today().normalize()
    options = ["YTD", "1Y", "3Y", "5Y", "Max"]
    default_idx = 1 if "1Y" in options else 0
    colA, colB, colC = st.columns([1, 1, 1])
    with colA:
        tf_choice = st.selectbox("Period", options, index=default_idx)
    with colB:
        bench = st.text_input("Benchmark (optional)", value="SPY", help="Pulled from your stock_prices via get_stock_prices.").upper().strip()
        if not bench:
            bench = None
    with colC:
        st.write("")  # spacer

    if items:
        if tf_choice == "YTD":
            start = pd.Timestamp(datetime(today.year, 1, 1))
        elif tf_choice == "1Y":
            start = today - pd.DateOffset(years=1)
        elif tf_choice == "3Y":
            start = today - pd.DateOffset(years=3)
        elif tf_choice == "5Y":
            start = today - pd.DateOffset(years=5)
        else:
            start = None

        with st.spinner("Computing portfolio history..."):
            res = compute_portfolio_history(items, start=start, end=None, benchmark_ticker=bench)

        nav_df = res["nav"]
        if nav_df is None or nav_df.empty:
            st.info("Not enough price data to compute portfolio NAV for the chosen period.")
            return

        metrics = res.get("metrics", {}) or {}
        bench_df = res.get("bench")
        drawdown_df = res.get("drawdown")
        contrib_df = res.get("contrib")
        weights_df = res.get("weights_current")
        corr_df = res.get("corr")

        # KPIs with tooltips
        k1, k2, k3, k4, k5 = st.columns(5)

        with k1:
            st.markdown(_tip_label("Total Return", "Final NAV vs initial NAV over the selected period."), unsafe_allow_html=True)
            st.metric(label="", value=f"{metrics.get('total_return_pct', 0):.2f}%")

        with k2:
            st.markdown(_tip_label("Annualized", "Geometric annualized rate implied by total return and period length."), unsafe_allow_html=True)
            ann = metrics.get('annualized_return_pct')
            st.metric(label="", value=("—" if ann is None else f"{ann:.2f}%"))

        with k3:
            st.markdown(_tip_label("Volatility", "Std dev of daily portfolio returns, annualized (×√252)."), unsafe_allow_html=True)
            vol = metrics.get('volatility_pct')
            st.metric(label="", value=("—" if vol is None else f"{vol:.2f}%"))

        with k4:
            st.markdown(_tip_label("Sharpe", "Annualized return ÷ annualized volatility (rf ≈ 0)."), unsafe_allow_html=True)
            sh = metrics.get('sharpe')
            st.metric(label="", value=("—" if sh is None else f"{sh:.2f}"))

        with k5:
            st.markdown(_tip_label("Max Drawdown", "Worst peak-to-trough decline in NAV during the period."), unsafe_allow_html=True)
            st.metric(label="", value=f"{metrics.get('max_drawdown_pct', 0):.2f}%")

        # NAV vs Benchmark
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=nav_df["date"], y=nav_df["nav"], mode="lines", name="Portfolio NAV"))
        if bench_df is not None and not bench_df.empty:
            fig.add_trace(go.Scatter(x=bench_df["date"], y=bench_df["bench_nav"], mode="lines", name="Benchmark"))
        fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

        # Drawdown
        if drawdown_df is not None and not drawdown_df.empty:
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(
                x=drawdown_df["date"], y=drawdown_df["drawdown"],
                mode="lines", name="Drawdown", fill="tozeroy"
            ))
            fig_dd.update_layout(title="Drawdown", height=240, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_dd, use_container_width=True)

        # Contribution (absolute P&L)
        if contrib_df is not None and not contrib_df.empty:
            fig_ctb = go.Figure()
            fig_ctb.add_trace(go.Bar(x=contrib_df["ticker"], y=contrib_df["pnl_abs"], name="P&L (abs)"))
            fig_ctb.update_layout(title="Per-ticker contribution (absolute)", height=300, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_ctb, use_container_width=True)

        # Current weights
        if weights_df is not None and not weights_df.empty:
            st.dataframe(
                weights_df.rename(columns={"ticker": "Ticker", "weight_now_pct": "Current Weight (%)"})
                          .style.format({"Current Weight (%)":"{:.2f}"}),
                use_container_width=True, height=220
            )

        # Correlation heatmap
        if corr_df is not None and not corr_df.empty:
            fig_corr = go.Figure(data=go.Heatmap(
                z=corr_df.values, x=corr_df.columns, y=corr_df.index,
                zmin=-1, zmax=1, colorbar=dict(title="ρ")
            ))
            fig_corr.update_layout(title="Holdings correlation (daily returns)", height=360, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.info("Add at least one stock (with a positive allocation) to analyze the portfolio.")
