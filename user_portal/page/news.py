# user_portal/page/news.py
from __future__ import annotations
import streamlit as st
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import pandas as pd
import re

from api.display_news import list_news, get_daily_summary

# --- Summary banner styles ---
BANNER_CSS = """
<style>
.summary-card{background:linear-gradient(135deg,#0b1020,#0a0f1a);
  border:1px solid #223047;border-radius:16px;padding:18px 20px;}
.summary-title{font-size:1.1rem;font-weight:700;margin:0 0 8px;
  display:flex;align-items:center;gap:.6rem}
.summary-badge{padding:2px 8px;border-radius:10px;font-size:.72rem;
  background:#1f2937;color:#9ca3af}
.summary-body p{margin:0 0 6px;line-height:1.55}
</style>
"""

def _normalize_para(txt: str) -> str:
    """Tidy LLM text: collapse spaces, drop leaked instructions,
    fix awkward spacing, end with punctuation."""
    t = (txt or "").strip()
    t = re.sub(r"\s+", " ", t)
    # remove any leaked instruction text
    t = re.sub(r"(?i)summarize the following.*$", "", t).strip()
    t = t.replace(" .", ".").replace(" ,", ",")
    # if we ended with an ellipsis or no punctuation, finish the sentence
    if t and t[-1] not in ".!?":
        t = t.rstrip("…") + "."
    return t

def render_daily_summary_card(s: dict, today: date):
    """Pretty summary banner with fallback badge if showing an older day."""
    if not s:
        return
    day_str = s.get("day")
    # title + stale badge if we’re showing a prior day
    is_stale = day_str and str(day_str) != today.isoformat()
    title = f"Daily Summary — {day_str or today.isoformat()}"
    badge = f'<span class="summary-badge">showing last available</span>' if is_stale else ""

    para1 = _normalize_para(s.get("summary", ""))
    para2 = _normalize_para(s.get("outlook", ""))

    st.markdown(BANNER_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-title">📰 {title} {badge}</div>
          <div class="summary-body">
            {'<p>'+para1+'</p>' if para1 else ''}
            {'<p><em>'+para2+'</em></p>' if para2 else ''}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _favicon(u: str | None):
    if not u:
        return None
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

def page(**kwargs):
    st.header("News")

    cols = st.columns(5)
    days   = cols[0].selectbox("Range", options=[7, 30, 90], index=1)
    limit  = cols[1].selectbox("Page size", options=[10, 20, 50], index=1)
    page_n = cols[2].number_input("Page", min_value=1, value=1, step=1)
    q      = cols[3].text_input("Search", value="", placeholder="keyword…")
    source = cols[4].text_input("Source", value="", placeholder="e.g., Reuters")

    if st.button("Refresh"):
        st.cache_data.clear()

    # Daily summary banner
    try:
        s = get_daily_summary(date.today())
    except Exception as e:
        s = None
        st.warning(f"Unable to load summary: {e}")

    if s:
        render_daily_summary_card(s, today=date.today())
    else:
        st.info("No daily summary yet.")

    # Articles
    try:
        rows = _load_news(days, q, source, limit, page_n)
    except Exception as e:
        st.error(f"Failed to load news: {e}")
        return

    if not rows:
        st.info("No articles found for the current filters.")
        return

    for a in rows:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4], vertical_alignment="top")
            img = a.get("image_url") or _favicon(a.get("canonical_url"))
            if img:
                c1.image(img, use_container_width=True)

            title = (a.get("title") or "").strip()
            url   = (a.get("canonical_url") or "").strip()
            c2.markdown(f"**[{title}]({url})**" if url else f"**{title}**")

            # show time in SG
            when = ""
            ts = a.get("published_at")
            if ts:
                try:
                    dt_sg = (pd.to_datetime(ts, utc=True)
                               .tz_convert(ZoneInfo("Asia/Singapore")))
                    when = dt_sg.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    when = ts.replace("T", " ")[:16]

            meta = " · ".join(x for x in [
                a.get("source") or a.get("author") or "",
                when,
            ] if x)
            if meta:
                c2.caption(meta)

            snippet = (a.get("snippet") or "").strip()
            if not snippet and a.get("content"):
                txt = a["content"]
                snippet = (txt[:200] + "…") if len(txt) > 200 else txt
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
