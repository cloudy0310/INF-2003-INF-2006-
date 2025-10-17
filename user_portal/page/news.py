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
.summary-card{
  border-radius:16px;
  padding:20px 22px;
  border:1px solid rgba(120,120,120,.18);
  background:linear-gradient(135deg,#0b1020,#0a0f1a);
  box-shadow:0 10px 24px rgba(2,6,23,.35), inset 0 1px 0 rgba(255,255,255,.03);
}
[data-theme="light"] .summary-card{
  background:linear-gradient(180deg,#ffffff,#f8fafc);
  border-color:rgba(0,0,0,.08);
  box-shadow:0 8px 20px rgba(2,6,23,.06), inset 0 1px 0 rgba(255,255,255,.8);
}

.summary-title{
  display:flex; align-items:center; gap:.6rem;
  font-size:1.15rem; font-weight:800; letter-spacing:.2px;
  margin:0 0 6px;
}
.summary-date{
  font-size:.78rem; padding:2px 10px; border-radius:999px;
  border:1px solid rgba(255,255,255,.18); color:#e5e7eb;
}
[data-theme="light"] .summary-date{
  border-color:rgba(0,0,0,.12); color:#111827; background:#eef2f7;
}

.summary-stale{
  margin-left:.25rem;
  font-size:.72rem; padding:2px 8px; border-radius:10px;
  background:#1f2937; color:#9ca3af; border:1px solid rgba(255,255,255,.15);
}
[data-theme="light"] .summary-stale{
  background:#f3f4f6; color:#111827; border-color:rgba(0,0,0,.1);
}

.summary-sentiment{
  margin-left:auto; font-size:.78rem; padding:2px 10px; border-radius:8px;
  border:1px solid transparent;
}
.sent-pos{ color:#16a34a; background:rgba(22,163,74,.14); border-color:rgba(22,163,74,.28); }
.sent-neg{ color:#ef4444; background:rgba(239,68,68,.14); border-color:rgba(239,68,68,.28); }
.sent-neu{ color:#6b7280; background:rgba(107,114,128,.14); border-color:rgba(107,114,128,.28); }

.summary-body{ font-size:.98rem; line-height:1.6; color:#e5e7eb; }
[data-theme="light"] .summary-body{ color:#0f172a; }
.summary-body p{ margin:0 0 8px; }
.summary-outlook{
  margin-top:.5rem; padding-top:.55rem;
  border-top:1px dashed rgba(255,255,255,.18);
  opacity:.98;
}
[data-theme="light"] .summary-outlook{ border-top-color:rgba(0,0,0,.12); }
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
    if not s:
        return

    day_str = s.get("day") or today.isoformat()
    is_stale = str(day_str) != today.isoformat()

    # Sentiment badge (optional; defaults to Neutral)
    score = s.get("sentiment_score", None)
    if score is None:
        sent_cls, sent_label = "sent-neu", "Neutral"
    elif score >= 0.15:
        sent_cls, sent_label = "sent-pos", f"Positive {score:+.2f}"
    elif score <= -0.15:
        sent_cls, sent_label = "sent-neg", f"Negative {score:+.2f}"
    else:
        sent_cls, sent_label = "sent-neu", f"Neutral {score:+.2f}"

    para1 = _normalize_para(s.get("summary", ""))
    para2 = _normalize_para(s.get("outlook", ""))

    st.markdown(BANNER_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="summary-card">
          <div class="summary-title">
            <span> Daily Summary</span>
            <span class="summary-date">{day_str}</span>
            {'<span class="summary-stale">showing last available</span>' if is_stale else ''}
          </div>
          <div class="summary-body">
            {'<p>'+para1+'</p>' if para1 else ''}
            {'<p class="summary-outlook"><em>Outlook:</em> '+para2+'</p>' if para2 else ''}
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
