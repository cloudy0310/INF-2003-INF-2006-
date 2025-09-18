# page/home.py
from __future__ import annotations
import math
import streamlit as st
from api.content import list_content, count_content

# ---------- Small compatibility helpers ----------

def _image_full_width(img):
    """
    Newer Streamlit: st.image(..., use_container_width=True)
    Older Streamlit: st.image(..., use_column_width=True)
    """
    try:
        st.image(img, use_container_width=True)
    except TypeError:
        # Fallback for older versions
        st.image(img, use_column_width=True)

def _columns_compat(spec, **kwargs):
    """
    Support 'vertical_alignment' only if the running Streamlit supports it.
    """
    try:
        return st.columns(spec, **kwargs)
    except TypeError:
        # Strip unknown kwargs (e.g., vertical_alignment on older versions)
        return st.columns(spec)

# ---------- Page ----------

def page(rds=None, dynamo=None):
    if rds is None:
        st.error("RDS engine not provided to page().")
        st.stop()

    st.title("🏠 Home")
    st.caption("Latest content from your RDS database.")

    f1, f2, f3, f4 = st.columns([1.0, 1.6, 1.6, 0.6])
    with f1:
        ticker = st.text_input("Filter by ticker", value="", placeholder="e.g., AAPL").upper().strip() or None
    with f2:
        tags_any = st.multiselect(
            "Tags (any)",
            options=[
                "news", "analysis", "education", "portfolio_tip", "market_update", "opinion",
                "ai", "semiconductors", "rsi", "macd", "diversification", "macro"
            ],
        ) or None
    with f3:
        search = st.text_input("Search title/excerpt", value="", placeholder="e.g., NVDA, RSI, CPI") or None
    with f4:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        # use_container_width exists for buttons in many versions; safe to keep.
        # If your Streamlit is *very* old and this errors, simply remove the kwarg.
        apply_clicked = st.button("Apply", use_container_width=True)

    st.markdown("---")

    if "content_page" not in st.session_state:
        st.session_state.content_page = 1
    if apply_clicked:
        st.session_state.content_page = 1

    pcol_l, pcol_prev, pcol_mid, pcol_next, pcol_ps = st.columns([0.6, 0.6, 2.2, 0.6, 1.0])
    with pcol_ps:
        page_size = st.selectbox("", [6, 12, 24], index=1, label_visibility="collapsed")

    # --- Count total rows ---
    try:
        total_rows = count_content(rds, ticker=ticker, tags_any=tags_any, search=search, only_published=True)
    except Exception as e:
        st.error(f"Failed to count content: {e}")
        st.stop()

    total_pages = max(1, math.ceil(total_rows / page_size))

    with pcol_prev:
        prev_disabled = st.session_state.content_page <= 1
        if st.button("←", disabled=prev_disabled):
            st.session_state.content_page = max(1, st.session_state.content_page - 1)

    with pcol_mid:
        st.caption(f"{total_rows} item(s) • Page {st.session_state.content_page} of {total_pages}")

    with pcol_next:
        next_disabled = st.session_state.content_page >= total_pages
        if st.button("→", disabled=next_disabled):
            st.session_state.content_page = min(total_pages, st.session_state.content_page + 1)

    st.markdown("---")

    # --- Fetch rows for current page ---
    try:
        rows = list_content(
            rds,
            page=st.session_state.content_page,
            page_size=page_size,
            ticker=ticker,
            tags_any=tags_any,
            search=search,
            only_published=True,
        )
    except Exception as e:
        st.error(f"Failed to fetch content: {e}")
        st.stop()

    st.markdown("### Latest content", unsafe_allow_html=True)

    if not rows:
        st.info("No content found with the current filters.")
        return

    for row in rows:
        _content_card(row)

# ---------- UI bits ----------

def _content_card(row: dict):
    with st.container():
        # Center alignment only on newer Streamlit; use compat helper
        c1, c2 = _columns_compat([1, 3], vertical_alignment="center")
        with c1:
            img = row.get("image_url")
            if img:
                _image_full_width(img)
        with c2:
            st.markdown(f"### {row.get('title') or 'Untitled'}")

            chips = []
            if row.get("content_type"):
                chips.append(_badge(row["content_type"]))
            if row.get("ticker"):
                chips.append(_badge(row["ticker"]))
            if row.get("published_at"):
                chips.append(_badge(f"📅 {row['published_at']}"))
            if chips:
                st.markdown("".join(chips), unsafe_allow_html=True)

            if row.get("excerpt"):
                st.write(row["excerpt"])

            tags = row.get("tags") or []
            if tags:
                tag_html = "".join(_tag_chip(t) for t in tags)
                st.markdown(tag_html, unsafe_allow_html=True)
    st.markdown("---")

def _badge(text: str) -> str:
    return (
        "<span style='background:#eef2ff;border:1px solid #dbeafe;color:#1e40af;"
        "padding:2px 8px;border-radius:999px;font-size:12px;margin-right:8px;white-space:nowrap;'>"
        f"{text}</span>"
    )

def _tag_chip(text: str) -> str:
    return (
        "<span style='background:#f4f4f5;border:1px solid #e7e7ea;color:#3f3f46;"
        "padding:2px 8px;border-radius:999px;font-size:12px;margin:0 6px 6px 0;display:inline-block;'>"
        f"{text}</span>"
    )
