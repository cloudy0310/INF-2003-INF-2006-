# app/views/user/news.py
from __future__ import annotations
import streamlit as st
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urlparse
import pandas as pd
from zoneinfo import ZoneInfo
from app.api.display_news import list_news, get_daily_summary

st.header("News")

# ----------------- Controls -----------------
cols = st.columns(5)
days   = cols[0].selectbox("Range", options=[7, 30, 90], index=1)
limit  = cols[1].selectbox("Page size", options=[10, 20, 50], index=1)
page   = cols[2].number_input("Page", min_value=1, value=1, step=1)
q      = cols[3].text_input("Search", value="", placeholder="keyword…")
source = cols[4].text_input("Source", value="", placeholder="e.g., Reuters")

refresh = st.button("Refresh", use_container_width=False)
if refresh:
    st.cache_data.clear()

# ----------------- Helpers -----------------
def _favicon(u: str | None):
    if not u: return None
    host = urlparse(u).netloc
    return f"https://www.google.com/s2/favicons?domain={host}&sz=128" if host else None

@st.cache_data(ttl=900)
def _load_news(days: int, q: str, source: str, limit: int, page: int):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    rows = list_news(
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        q=q or None,
        source=source or None,
        limit=limit,
        page=page,
    )
    return rows

SG = ZoneInfo("Asia/Singapore")
def to_sgt(iso_str: str | None) -> str:
    if not iso_str:
        return ""
    # ensure the ISO string is timezone-aware
    dt_utc = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt_utc.astimezone(SG).strftime("%Y-%m-%d %H:%M SGT")

# ----------------- Daily summary banner -----------------
today_summary = get_daily_summary(date.today())
if today_summary:
    with st.container(border=True):
        st.subheader("Daily Summary")
        st.write(today_summary.get("summary", ""))
        if today_summary.get("outlook"):
            st.caption(today_summary["outlook"])
else:
    st.info("No daily summary yet.")

# ----------------- Card list -----------------
rows = _load_news(days, q, source, limit, page)
if not rows:
    st.info("No articles found for the current filters.")
else:
    for a in rows:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4], vertical_alignment="top")
            img = a.get("image_url") or _favicon(a.get("canonical_url"))
            if img:
                c1.image(img, use_container_width=True)
            title = (a.get("title") or "").strip()
            url   = (a.get("canonical_url") or "").strip()
            c2.markdown(f"**[{title}]({url})**" if url else f"**{title}**")
            meta = " · ".join(
                x for x in [
                    a.get("source") or a.get("author") or "",
                    to_sgt(a.get("published_at")),  # <-- show in SGT
                ] if x
            )
            if meta:
                c2.caption(meta)
            # Prefer snippet; fall back to first ~200 chars of content if snippet missing
            snippet = (a.get("snippet") or "")[:300]
            if not snippet and a.get("content"):
                snippet = (a["content"][:200] + "…") if len(a["content"]) > 200 else a["content"]
            if snippet:
                c2.write(snippet)

    # Download current page
    df = pd.DataFrame(rows)
    st.download_button(
        "Download news CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name="news.csv",
        mime="text/csv",
    )
