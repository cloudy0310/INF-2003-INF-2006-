# pipeline_scripts/pipeline/fetch_news_daily.py
from __future__ import annotations
import os, re, json, time, hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs, quote_plus
import requests, feedparser
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# ----------------- Config -----------------
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
FULLTEXT_TIMEOUT = 12     # seconds
FULLTEXT_MAX_CHARS = 12000

SUPABASE_URL          = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
HF_TOKEN              = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
HF_MODEL              = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")

REST = f"{SUPABASE_URL}/rest/v1"
HDRS = {
    "apikey": SUPABASE_SERVICE_ROLE,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation",
}

N_GENERAL  = int(os.getenv("NEWS_N_GENERAL", "5"))
N_SPECIFIC = int(os.getenv("NEWS_N_SPECIFIC", "5"))
USER_SEARCH = os.getenv("NEWS_SEARCH", "")
TICKERS_ENV = os.getenv("TICKERS", "")

# ----------------- Utilities -----------------

def build_specific_queries(user_search: str, tickers_csv: str) -> List[str]:
    qs: List[str] = []
    user_search = (user_search or "").strip()
    if user_search:
        qs.append(user_search)

    tickers = [t.strip() for t in tickers_csv.split(",") if t.strip()]
    for t in tickers:
        qs.append(f'("{t}" OR {t} stock OR {t} shares)')
    return qs

def pick_top_per_bucket(general_items, specific_items, n_general, n_specific):
    gen_ranked = dedupe_and_rank(general_items, top_k=n_general*4 or 20)
    spc_ranked = dedupe_and_rank(specific_items, top_k=n_specific*4 or 20)

    seen = set()
    def add(lst, n):
        out = []
        for a in lst:
            key = article_id_for(a.get("url",""), a.get("title",""))
            if key in seen: 
                continue
            seen.add(key)
            out.append(a)
            if len(out) >= n:
                break
        return out

    chosen_general  = add(gen_ranked, n_general)
    chosen_specific = add(spc_ranked, n_specific)

    # If one bucket was thin, top up from the other
    total_needed = n_general + n_specific
    combined = chosen_general + chosen_specific
    if len(combined) < total_needed:
        pool = [a for a in gen_ranked + spc_ranked if article_id_for(a.get("url",""), a.get("title","")) not in seen]
        for a in pool:
            combined.append(a); seen.add(article_id_for(a.get("url",""), a.get("title","")))
            if len(combined) >= total_needed:
                break

    # Sort final by score then recency
    combined.sort(key=lambda x: (x.get("score",0), x.get("published_ts") or 0), reverse=True)
    return combined

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

def google_news_rss(
    q: str,
    lang: str = "en-US",
    country: str = "US",
    max_items: int = 120,
    start_date: str | None = None,   # "YYYY-MM-DD"
    end_date: str | None = None,     # "YYYY-MM-DD"
) -> List[Dict[str, Any]]:
    # Date qualifiers help Google News return older results
    if start_date and end_date:
        q = f"({q}) after:{start_date} before:{end_date}"

    enc_q = quote_plus(q, safe="")
    lang_code = lang.split("-")[0]
    url = f"https://news.google.com/rss/search?q={enc_q}&hl={lang}&gl={country}&ceid={country}:{lang_code}"

    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    out = []
    for e in feed.get("entries", [])[:max_items]:
        source = None
        if isinstance(e.get("source"), dict):
            source = e["source"].get("title")
        out.append({
            "title": (e.get("title") or "").strip(),
            "url": canonical_url(e.get("link","")),
            "source": normalize_source(source),
            "author": None,
            "snippet": BeautifulSoup((e.get("summary") or ""), "lxml").get_text(" ", strip=True),
            "image": pick_image(e),
            "published_ts": dt_to_epoch(e),
        })
    return out

def fetch_fulltext(url: str) -> Optional[str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        html = r.text

        # 1) Try AMP if available (often cleaner)
        soup = BeautifulSoup(html, "lxml")
        amp = soup.find("link", rel=lambda v: v and "amphtml" in v.lower())
        if amp and amp.get("href"):
            try:
                rr = requests.get(amp["href"], headers=headers, timeout=15)
                rr.raise_for_status()
                html = rr.text
                soup = BeautifulSoup(html, "lxml")
            except Exception:
                pass

        # 2) Readability extraction
        doc = Document(html)
        main_html = doc.summary()
        text = " ".join(BeautifulSoup(main_html, "lxml").stripped_strings)

        # 3) JSON-LD articleBody fallback
        if len(text) < 400:
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(s.string or "")
                except Exception:
                    continue
                if isinstance(data, dict):
                    candidates = [data]
                elif isinstance(data, list):
                    candidates = data
                else:
                    candidates = []
                for d in candidates:
                    if not isinstance(d, dict):
                        continue
                    t = (d.get("@type") or d.get("type") or "").lower()
                    if "article" in t and d.get("articleBody"):
                        text2 = str(d["articleBody"]).strip()
                        if len(text2) > len(text):
                            text = text2
                if len(text) >= 400:
                    break

        # 4) DOM fallbacks (<article>, then all <p>)
        if len(text) < 400:
            art = soup.find("article")
            if art:
                text2 = " ".join(art.get_text(" ", strip=True).split())
                if len(text2) > len(text):
                    text = text2

        if len(text) < 400:
            paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            text2 = " ".join(paras)
            if len(text2) > len(text):
                text = text2

        text = text.strip()
        if not text:
            return None
        if len(text) > FULLTEXT_MAX_CHARS:
            text = text[:FULLTEXT_MAX_CHARS]
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

def dedupe_and_rank(items: List[Dict[str, Any]], top_k: int = 30) -> List[Dict[str, Any]]:
    now_ts = int(time.time())
    best: Dict[str, Dict[str, Any]] = {}
    for a in items:
        key = title_key(a.get("title","")) or a.get("url","")
        a["score"] = score_item(a, now_ts)
        if key not in best or a["score"] > best[key]["score"]:
            best[key] = a
    ranked = sorted(best.values(), key=lambda x: (x.get("score",0), x.get("published_ts") or 0), reverse=True)
    return ranked[:top_k]

# -------- Supabase (REST) --------
def article_id_for(url: str, title: str) -> str:
    base = url or title
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def upsert_articles(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows: return []
    url = f"{REST}/news_articles?on_conflict=canonical_url"
    r = requests.post(url, headers=HDRS, data=json.dumps(rows), timeout=45)
    r.raise_for_status()
    return r.json()

def upsert_daily_summary(day: datetime.date, payload: Dict[str, Any]) -> None:
    url = f"{REST}/news_daily_summary?on_conflict=day"
    r = requests.post(url, headers=HDRS, data=json.dumps({
        "day": day.isoformat(),
        "summary": payload.get("summary",""),
        "outlook": payload.get("outlook",""),
        "sentiment_score": payload.get("sentiment_score"),
        "article_ids": payload.get("article_ids", []),
    }), timeout=30)
    r.raise_for_status()

# -------- HF summarizer (optional) --------
def _clip(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"

def summarize_with_hf(articles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not HF_TOKEN:
        return None
    arts = sorted(articles, key=lambda a: a.get("published_ts") or 0, reverse=True)[:12]
    bullets = []
    for a in arts:
        dt = datetime.fromtimestamp(a["published_ts"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if a.get("published_ts") else ""
        bullets.append(f"- [{dt}] {_clip(a.get('title',''), 140)} ({a.get('source','')})")
    system = (
        "You are a careful financial writer. Use only the provided bullet list.\n"
        "Write TWO short paragraphs:\n"
        "(1) Recent developments (facts-only; 3–4 sentences)\n"
        "(2) Outlook (cautious; 2–3 sentences)\n"
        "Avoid advice, targets, speculation."
    )
    prompt = system + "\n\nARTICLES:\n" + "\n".join(bullets)
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 320, "temperature": 0.4}}
    r = requests.post(api_url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        gen = data[0]["generated_text"]
    elif isinstance(data, dict) and "generated_text" in data:
        gen = data["generated_text"]
    else:
        gen = str(data)
    parts = [p.strip() for p in gen.strip().split("\n\n") if p.strip()]
    return {
        "summary": parts[0] if parts else gen.strip(),
        "outlook": parts[1] if len(parts) > 1 else "",
        "article_ids": [article_id_for(a.get("url",""), a.get("title","")) for a in arts],
        "sentiment_score": None,
    }

# ----------------- Main -----------------
def run(top_k: int = 25, lang="en-US", country="US") -> None:
    # -------- fetch: general bucket --------
    fetched_general: List[Dict[str, Any]] = []
    for q in QUERIES:
        fetched_general.extend(
            google_news_rss(q=q, lang=lang, country=country, max_items=120)
        )

    # -------- fetch: specific bucket (user search + tickers) --------
    fetched_specific: List[Dict[str, Any]] = []
    spec_qs = build_specific_queries(USER_SEARCH, TICKERS_ENV)
    for q in spec_qs:
        fetched_specific.extend(
            google_news_rss(q=q, lang=lang, country=country, max_items=120)
        )

    # fill "author" with publisher/outlet
    for a in (fetched_general + fetched_specific):
        if not a.get("author") and a.get("source"):
            a["author"] = a["source"]

    # -------- choose N per bucket (dedupe across buckets) --------
    # If user didn't provide specific queries, this still returns just the general picks.
    ranked = pick_top_per_bucket(
        general_items=fetched_general,
        specific_items=fetched_specific,
        n_general=N_GENERAL,
        n_specific=N_SPECIFIC,
    )

    # -------- fulltext (scrape) for the chosen set --------
    for a in ranked:
        if not a.get("content"):
            a["content"] = fetch_fulltext(a["url"])

    # -------- upsert to Supabase --------
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
            "score": a.get("score"),
            "raw": None,
        })
    saved = upsert_articles(rows)
    print(f"[daily] upserted {len(saved)} articles")

    # -------- daily summary (optional, uses the final ranked set) --------
    today = datetime.now(timezone.utc).date()
    todays = [
        a for a in ranked
        if a.get("published_ts") and
           datetime.fromtimestamp(a["published_ts"], tz=timezone.utc).date() == today
    ]
    if HF_TOKEN and todays:
        summ = summarize_with_hf(todays)
        if summ:
            upsert_daily_summary(today, summ)
            print("[daily] saved daily summary")
    else:
        print("[daily] skipped summary (no token or no articles)")


if __name__ == "__main__":
    missing = [k for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE") if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")
    run()
