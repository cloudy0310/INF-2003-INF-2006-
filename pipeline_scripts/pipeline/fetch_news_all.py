# pipeline_scripts/pipeline/fetch_news_all.py
from __future__ import annotations
import os, re, json, time, hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
import requests, feedparser
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

QUERIES = [
    'stock market OR equities OR "S&P 500" OR Dow OR Nasdaq',
    'markets today OR premarket OR futures',
    'earnings OR guidance',
]
GOOD_SOURCES_WEIGHT = {
    "Reuters": 1.0, "Bloomberg": 0.95, "Financial Times": 0.9, "WSJ": 0.9,
    "CNBC": 0.8, "The Economist": 0.8, "Yahoo Finance": 0.6, "MarketWatch": 0.6,
}
SIGNAL_WORDS = {
    r"\b(surges?|plunges?|spikes?|tumbles?)\b": 0.6,
    r"\b(earnings|EPS|guidance|outlook|downgrade|upgrade)\b": 0.5,
    r"\b(M&A|acquisition|merger|spin[- ]off)\b": 0.4,
    r"\b(SEC filing|lawsuit|investigation)\b": 0.4,
    r"\b(dividend|buyback|split)\b": 0.3,
}
FULLTEXT_TIMEOUT = 12
FULLTEXT_MAX_CHARS = 12000

SUPABASE_URL          = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
REST = f"{SUPABASE_URL}/rest/v1"
HDRS = {
    "apikey": SUPABASE_SERVICE_ROLE,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation",
}

def normalize_source(name: Optional[str]) -> Optional[str]:
    if not name: return None
    return re.sub(r"\s+", " ", name).strip()

def title_key(title: str) -> str:
    t = re.sub(r"[^a-z0-9 ]+", "", (title or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.md5(t.encode()).hexdigest()

def canonical_url(u: str) -> str:
    try:
        if "news.google.com/rss/articles" in u:
            q = parse_qs(urlparse(u).query)
            if "url" in q and q["url"]:
                return q["url"][0]
    except Exception:
        pass
    return u

def pick_image(entry: Dict[str, Any]) -> Optional[str]:
    for key in ("media_thumbnail", "media_content"):
        v = entry.get(key)
        if isinstance(v, list) and v:
            u = v[0].get("url")
            if u: return u
        if isinstance(v, dict):
            u = v.get("url")
            if u: return u
    for l in entry.get("links", []) or []:
        if l.get("rel") == "enclosure" and str(l.get("type","")).startswith("image/"):
            return l.get("href")
    try:
        real = canonical_url(entry.get("link",""))
        host = urlparse(real).netloc or urlparse(entry.get("link","")).netloc
        if host:
            return f"https://www.google.com/s2/favicons?domain={host}&sz=128"
    except Exception:
        pass
    return None

def dt_to_epoch(entry: Dict[str, Any]) -> Optional[int]:
    for k in ("published_parsed", "updated_parsed"):
        dt = entry.get(k)
        if dt:
            try: return int(time.mktime(dt))
            except Exception: pass
    return None

def google_news_rss(q: str, lang="en-US", country="US", max_items=120) -> List[Dict[str, Any]]:
    url = f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={country}:{lang.split('-')[0]}"
    feed = feedparser.parse(url)
    out = []
    for e in feed.get("entries", [])[:max_items]:
        source = None
        if isinstance(e.get("source"), dict):
            source = e["source"].get("title")
        out.append({
            "title": (e.get("title") or "").strip(),
            "url": canonical_url(e.get("link","")),
            "source": normalize_source(source),
            "author": None,  # will fill with source
            "snippet": BeautifulSoup((e.get("summary") or ""), "lxml").get_text(" ", strip=True),
            "image": pick_image(e),
            "published_ts": dt_to_epoch(e),
        })
    return out

def fetch_fulltext(url: str) -> Optional[str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
        r = requests.get(url, headers=headers, timeout=FULLTEXT_TIMEOUT)
        r.raise_for_status()
        html = r.text
        doc = Document(html)
        main_html = doc.summary()
        text = " ".join(BeautifulSoup(main_html, "lxml").stripped_strings)
        if len(text) < 300:
            soup = BeautifulSoup(html, "lxml")
            paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            text2 = " ".join(paras)
            if len(text2) > len(text): text = text2
        text = text.strip()
        if not text: return None
        if len(text) > FULLTEXT_MAX_CHARS: text = text[:FULLTEXT_MAX_CHARS]
        return text
    except Exception:
        return None

def score_item(a: Dict[str, Any], now_ts: int) -> float:
    if a.get("published_ts"):
        age_h = max(0.0, (now_ts - int(a["published_ts"])) / 3600.0)
        recency = max(0.0, 1.0 - min(age_h / 48.0, 1.0))
    else:
        recency = 0.2
    sw = GOOD_SOURCES_WEIGHT.get(a.get("source",""), 0.5)
    sig = 0.0
    for pat, w in SIGNAL_WORDS.items():
        if re.search(pat, a.get("title",""), re.IGNORECASE):
            sig = max(sig, w)
    return round(0.55*recency + 0.30*sw + 0.15*sig, 4)

def dedupe_and_rank(items: List[Dict[str, Any]], top_k: int = 40) -> List[Dict[str, Any]]:
    now_ts = int(time.time())
    best: Dict[str, Dict[str, Any]] = {}
    for a in items:
        key = title_key(a.get("title","")) or a.get("url","")
        a["score"] = score_item(a, now_ts)
        if key not in best or a["score"] > best[key]["score"]:
            best[key] = a
    return sorted(best.values(), key=lambda x: (x.get("score",0), x.get("published_ts") or 0), reverse=True)[:top_k]

# Supabase
def article_id_for(url: str, title: str) -> str:
    base = url or title
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def upsert_articles(rows: List[Dict[str, Any]], supabase_url: str, service_role: str) -> None:
    if not rows: return
    rest = f"{supabase_url}/rest/v1/news_articles?on_conflict=canonical_url"
    hdrs = {
        "apikey": service_role,
        "Authorization": f"Bearer {service_role}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    r = requests.post(rest, headers=hdrs, data=json.dumps(rows), timeout=60)
    r.raise_for_status()

def run_backfill(start_date: str, end_date: str, step_days: int = 7, per_step_top_k: int = 40, lang="en-US", country="US"):
    supabase_url = SUPABASE_URL
    service_role = SUPABASE_SERVICE_ROLE
    start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    end   = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)

    t0 = start
    while t0 < end:
        t1 = min(t0 + timedelta(days=step_days), end)

        fetched: List[Dict[str, Any]] = []
        for q in QUERIES:
            fetched.extend(google_news_rss(q=q, lang=lang, country=country, max_items=120))

        # fill "author" with publisher/outlet
        for a in fetched:
            if not a.get("author") and a.get("source"):
                a["author"] = a["source"]

        # filter window + rank
        in_win = [a for a in fetched if a.get("published_ts") and t0 <= datetime.fromtimestamp(a["published_ts"], tz=timezone.utc) < t1]
        ranked = dedupe_and_rank(in_win, top_k=per_step_top_k)

        # fulltext scrape for each ranked item
        for a in ranked:
            if not a.get("content"):
                a["content"] = fetch_fulltext(a["url"])

        rows = []
        for a in ranked:
            pub_dt = (
                datetime.fromtimestamp(a["published_ts"], tz=timezone.utc)
                if a.get("published_ts") else None
            )
            rows.append({
                "article_id": article_id_for(a["url"], a["title"]),
                "title": a["title"],
                "canonical_url": a["url"],
                "source": a.get("source"),
                "author": a.get("author"),
                "snippet": a.get("snippet"),
                "content": a.get("content"),
                "image_url": a.get("image"),
                "published_at": pub_dt.isoformat() if pub_dt else None,
                "day": pub_dt.date().isoformat() if pub_dt else None,
                "published_time": pub_dt.strftime("%H:%M:%S") if pub_dt else None,
                "score": a.get("score"),
                "raw": None,
            })
        upsert_articles(rows, supabase_url, service_role)
        print(f"[backfill] {t0.date()} → {t1.date()} : upserted {len(rows)}")
        t0 = t1

if __name__ == "__main__":
    missing = [k for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE") if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=365)).isoformat()
    run_backfill(start_date=start, end_date=today.isoformat())
