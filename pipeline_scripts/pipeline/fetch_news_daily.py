# pipeline_scripts/pipeline/fetch_news_daily.py
from __future__ import annotations
import os, re, json, time, hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs, quote_plus, urljoin
import requests, feedparser
from bs4 import BeautifulSoup
from readability import Document
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())
from google import genai


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_GEMINI = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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

ARTICLE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://news.google.com/",
}

SUPABASE_URL          = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")

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

def fetch_article(url: str) -> tuple[Optional[str], Optional[str]]:
    try:
        r = requests.get(url, headers=ARTICLE_HEADERS, timeout=FULLTEXT_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        html = r.text
        base = r.url
        soup = BeautifulSoup(html, "lxml")

        amp = soup.find("link", rel=lambda v: v and "amphtml" in v.lower())
        if amp and amp.get("href"):
            try:
                rr = requests.get(urljoin(base, amp["href"]), headers=ARTICLE_HEADERS, timeout=FULLTEXT_TIMEOUT)
                rr.raise_for_status()
                html = rr.text
                base = rr.url
                soup = BeautifulSoup(html, "lxml")
            except Exception:
                pass

        try:
            doc = Document(html)
            main_html = doc.summary() or ""
            text = " ".join(BeautifulSoup(main_html, "lxml").stripped_strings).strip()
        except Exception:
            text = ""

        if len(text) < 400:
            def visit(node):
                nonlocal text
                if isinstance(node, dict):
                    typ = str(node.get("@type") or node.get("type") or "").lower()
                    if "article" in typ and node.get("articleBody"):
                        cand = str(node["articleBody"]).strip()
                        if len(cand) > len(text):
                            text = cand
                    for v in node.values():
                        visit(v)
                elif isinstance(node, list):
                    for v in node:
                        visit(v)
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    visit(json.loads(s.string or ""))
                except Exception:
                    continue
                if len(text) >= 400:
                    break

        if len(text) < 400:
            node = soup.find("article") or soup.find("main")
            if node:
                cand = " ".join(node.get_text(" ", strip=True).split())
                if len(cand) > len(text):
                    text = cand

        if len(text) < 400:
            paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            cand = " ".join(paras).strip()
            if len(cand) > len(text):
                text = cand

        if text and len(text) > FULLTEXT_MAX_CHARS:
            text = text[:FULLTEXT_MAX_CHARS]

        img = None
        for key, val in (("property", "og:image"),
                         ("name", "twitter:image"),
                         ("property", "og:image:url")):
            tag = soup.find("meta", attrs={key: val})
            if tag and tag.get("content"):
                img = urljoin(base, tag["content"].strip()); break
        if not img:
            tag = soup.find("link", attrs={"rel": "image_src"}) or soup.find("meta", attrs={"itemprop": "image"})
            if tag:
                c = (tag.get("href") or tag.get("content") or "").strip()
                if c:
                    img = urljoin(base, c)

        return (text or None), (img or None)
    except Exception:
        return None, None

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

# -------- summarizer (optional) --------
def _clip(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"

def _get_prev_summary(day: datetime.date) -> Optional[Dict[str, Any]]:
    params = {
        "select": "*",
        "order": "day.desc",
        "limit": "1",
        "day": f"lt.{day.isoformat()}",
    }
    r = requests.get(f"{REST}/news_daily_summary", headers=HDRS, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None

def summarize_with_gemini(articles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Summarize with Google Gemini (new client) into two short paragraphs."""
    if not _GEMINI:
        return None

    MAX_ARTS = int(os.getenv("SUMMARY_MAX_ARTS", "10"))
    arts = sorted(articles, key=lambda a: a.get("published_ts") or 0, reverse=True)[:MAX_ARTS]

    def _clip(s: str, n: int) -> str:
        s = " ".join((s or "").split())
        return s if len(s) <= n else s[:n] + "…"

    bullets = []
    for a in arts:
        dt = ""
        if a.get("published_ts"):
            dt = datetime.fromtimestamp(a["published_ts"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        bullets.append(f"- [{dt}] {_clip(a.get('title',''), 140)} ({_clip(a.get('source',''), 40)})")

    prompt = (
        "You are a financial news editor writing a neutral daily market brief. "
        "Write exactly TWO paragraphs:\n"
        "1) Recent developments (3–4 full sentences; factual; no quotes)\n"
        "2) Outlook (2–3 balanced sentences; cautious; no advice/targets)\n"
        "Do not copy headlines verbatim. No bullets, no meta-text, no ellipses.\n\n"
        "ARTICLES:\n" + "\n".join(bullets)
    )

    temperature = float(os.getenv("SUMMARY_TEMPERATURE", "0.2"))
    max_tokens  = int(os.getenv("GEMINI_MAX_TOKENS", "320"))
    retries     = int(os.getenv("GEMINI_MAX_RETRIES", "4"))

    # try the env model first, then a few sensible fallbacks
    primary   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest")
    fallbacks = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro"]
    models_to_try = [m for i, m in enumerate([primary] + fallbacks) if m and m not in ([primary] + fallbacks)[:i]]

    last_err = None
    text, used_model = None, None

    for model in models_to_try:
        for attempt in range(retries):
            try:
                resp = _GEMINI.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"temperature": temperature, "max_output_tokens": max_tokens}
                )
                text = (resp.text or "").strip()
                if not text:
                    raise RuntimeError("Empty Gemini response")
                used_model = model
                break
            except Exception as e:
                last_err = e
                # If the model isn't available for your key, move on immediately
                if "404" in str(e) or "not found" in str(e).lower():
                    break
                time.sleep(2 * (attempt + 1))
        if text:
            break

    if not text:
        print(f"[daily] Gemini summary failed after retries: {last_err}")
        return None
    else:
        print(f"[daily] Gemini summary used model={used_model}")

    # Normalize & make sure there are two paragraphs ending cleanly
    parts = [p.strip() for p in text.replace("\u2026", "...").split("\n\n") if p.strip()]
    if len(parts) < 2:
        sents = re.split(r"(?<=[.!?])\s+", text.strip())
        mid = max(1, len(sents)//2)
        parts = [" ".join(sents[:mid]), " ".join(sents[mid:])]
    parts = [(p.rstrip(" .") + ".") for p in parts[:2]]

    return {
        "summary": parts[0],
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

    # -------- enrich: fulltext + thumbnail --------
    enriched: List[Dict[str, Any]] = []
    for a in ranked:
        needs_img = not a.get("image") or "google.com/s2/favicons" in str(a.get("image"))
        if not a.get("content") or needs_img:
            body, ogimg = fetch_article(a["url"])
            if body and not a.get("content"):
                a["content"] = body
            if ogimg and needs_img:
                a["image"] = ogimg

        # last resort: keep a non-empty snippet as content so UI never looks blank
        if not a.get("content") and a.get("snippet"):
            snip = a["snippet"].strip()
            if snip:
                a["content"] = snip

        enriched.append(a)

    # honor top_k consistently (DB + summary)
    selected = enriched[:top_k]

    # -------- upsert to Supabase --------
    rows = []
    for a in selected:
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

    # -------- daily summary --------
    now = datetime.now(timezone.utc)
    today = now.date()

    # strict "today" first
    todays = [
        a for a in selected
        if a.get("published_ts") and
           datetime.fromtimestamp(a["published_ts"], tz=timezone.utc).date() == today
    ]

    recent_window_h = int(os.getenv("SUMMARY_RECENT_HOURS", "36"))
    recent = [
        a for a in selected
        if a.get("published_ts") and
           (now - datetime.fromtimestamp(a["published_ts"], tz=timezone.utc)).total_seconds() <= recent_window_h * 3600
    ]

    cand = todays if todays else recent
    print(f"[daily] summary candidates — today={len(todays)} recent({recent_window_h}h)={len(recent)} model={GEMINI_MODEL}")

    if GEMINI_API_KEY and cand:
        summ = summarize_with_gemini(cand)
        if summ:
            upsert_daily_summary(today, summ)
            src = "today" if cand is todays else f"recent{recent_window_h}h"
            print(f"[daily] saved daily summary from {src} (n={len(cand)})")
        else:
            prev = _get_prev_summary(today)
            if prev:
                upsert_daily_summary(today, {
                    "summary": prev.get("summary",""),
                    "outlook": prev.get("outlook",""),
                    "sentiment_score": prev.get("sentiment_score"),
                    "article_ids": prev.get("article_ids", []),
                })
                print("[daily] Gemini failed; copied yesterday's summary")
            else:
                print("[daily] Gemini failed and no previous summary to copy")
    else:
        prev = _get_prev_summary(today)
        if prev:
            upsert_daily_summary(today, {
                "summary": prev.get("summary",""),
                "outlook": prev.get("outlook",""),
                "sentiment_score": prev.get("sentiment_score"),
                "article_ids": prev.get("article_ids", []),
            })
            print("[daily] no candidates/key; copied yesterday's summary")
        else:
            print("[daily] skipped summary (no candidates and no previous summary)")



if __name__ == "__main__":
    missing = [k for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE") if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")
    run()
