# pipeline_scripts/pipeline/fetch_news_all.py
from __future__ import annotations
import os, re, json, time, hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs, quote_plus, urljoin, urlsplit, urlunsplit
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
FULLTEXT_TIMEOUT = 12
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
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
IMG_BAD_PAT = re.compile(
    r"(sprite|favicon|logo|brand|icon|placeholder|1x1|blank|data:image|default|avatar|transparent|pixel)",
    re.I
)

SUPABASE_URL          = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
REST = f"{SUPABASE_URL}/rest/v1"
HDRS = {
    "apikey": SUPABASE_SERVICE_ROLE,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation",
}

N_GENERAL   = int(os.getenv("NEWS_N_GENERAL", "5"))
N_SPECIFIC  = int(os.getenv("NEWS_N_SPECIFIC", "5"))
USER_SEARCH = os.getenv("NEWS_SEARCH", "")
TICKERS_ENV = os.getenv("TICKERS", "")

# ----------------- Utilities -----------------
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

def _norm_url(u: str) -> str:
    try:
        sp = urlsplit(u or "")
        # strip query+fragment to reduce dupes
        return urlunsplit((sp.scheme, sp.netloc, sp.path, "", ""))
    except Exception:
        return (u or "").strip()

def _img_url_from_tag(tag, base):
    if not tag:
        return None
    for attr in ("data-src", "data-original", "srcset", "src"):
        val = tag.get(attr)
        if not val:
            continue
        if attr == "srcset":
            first = val.split(",")[0].strip().split(" ")[0]
            u = first
        else:
            u = val.strip()
        if u:
            return urljoin(base, u)
    return None

def _jsonld_images(soup, base):
    out = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        def collect(node):
            if isinstance(node, dict):
                img = node.get("image")
                if img:
                    if isinstance(img, str):
                        out.append(urljoin(base, img))
                    elif isinstance(img, dict):
                        for k in ("url", "contentUrl"):
                            if img.get(k): out.append(urljoin(base, img[k]))
                    elif isinstance(img, list):
                        for it in img:
                            if isinstance(it, str):
                                out.append(urljoin(base, it))
                            elif isinstance(it, dict):
                                for k in ("url","contentUrl"):
                                    if it.get(k): out.append(urljoin(base, it[k]))
                for v in node.values(): collect(v)
            elif isinstance(node, list):
                for v in node: collect(v)
        collect(data)
    return out

def _has_real_img(a: Dict[str, Any]) -> bool:
    u = (a.get("image") or a.get("image_url") or "")
    return bool(u) and "google.com/s2/favicons" not in u and "gstatic" not in u

def _dedupe_articles(arts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Collapse duplicates by normalized canonical URL and by (source, title_key).
    Prefer: real image > higher score > newer.
    """
    def key_url(a): return _norm_url(a.get("url") or a.get("canonical_url") or "")
    def key_src_title(a): return (a.get("source") or "", title_key(a.get("title","")))

    def rank(a):
        return (
            1 if _has_real_img(a) else 0,
            float(a.get("score") or 0),
            int(a.get("published_ts") or 0),
        )

    by_url: Dict[str, Dict[str, Any]] = {}
    by_src_t: Dict[tuple, Dict[str, Any]] = {}
    def choose(old, new): return new if rank(new) > rank(old) else old

    for a in arts:
        ku = key_url(a)
        if ku:
            by_url[ku] = choose(by_url[ku], a) if ku in by_url else a
        kst = key_src_title(a)
        if kst:
            by_src_t[kst] = choose(by_src_t[kst], a) if kst in by_src_t else a

    merged = list({id(v): v for v in [*by_url.values(), *by_src_t.values()]}.values())
    final_by_url: Dict[str, Dict[str, Any]] = {}
    for a in merged:
        ku = key_url(a)
        if not ku: 
            continue
        final_by_url[ku] = choose(final_by_url[ku], a) if ku in final_by_url else a
    return list(final_by_url.values())

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
            key = article_id_for(_norm_url(a.get("url","")), a.get("title",""))
            if key in seen:
                continue
            seen.add(key)
            out.append(a)
            if len(out) >= n:
                break
        return out

    chosen_general  = add(gen_ranked, n_general)
    chosen_specific = add(spc_ranked, n_specific)

    total_needed = n_general + n_specific
    combined = chosen_general + chosen_specific
    if len(combined) < total_needed:
        pool = [a for a in gen_ranked + spc_ranked
                if article_id_for(_norm_url(a.get("url","")), a.get("title","")) not in seen]
        for a in pool:
            combined.append(a)
            seen.add(article_id_for(_norm_url(a.get("url","")), a.get("title","")))
            if len(combined) >= total_needed:
                break

    combined.sort(key=lambda x: (x.get("score",0), x.get("published_ts") or 0), reverse=True)
    return combined

def pick_image(entry: Dict[str, Any]) -> Optional[str]:
    for key in ("media_thumbnail", "media_content"):
        v = entry.get(key)
        cand = None
        if isinstance(v, list) and v and isinstance(v[0], dict):
            cand = v[0].get("url")
        elif isinstance(v, dict):
            cand = v.get("url")
        if cand:
            u = cand.strip()
            if u and "google.com/s2/favicons" not in u and "gstatic" not in u:
                return u
    for l in entry.get("links", []) or []:
        if l.get("rel") == "enclosure" and str(l.get("type","")).startswith("image/"):
            u = (l.get("href") or "").strip()
            if u:
                return u
    try:
        real = canonical_url(entry.get("link","")) or entry.get("link","")
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
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict[str, Any]]:
    if start_date and end_date:
        q = f"({q}) after:{start_date} before:{end_date}"
    enc_q = quote_plus(q, safe="")
    lang_code = lang.split("-")[0]
    url = f"https://news.google.com/rss/search?q={enc_q}&hl={lang}&gl={country}&ceid={country}:{lang_code}"

    resp = requests.get(url, headers=ARTICLE_HEADERS, timeout=20)
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

def _get(url, headers, timeout):
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r

def fetch_article(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch an article and return (main_text, best_image_url).
    Includes AMP fallback, Readability, JSON-LD/article/main/p merges,
    richer image extraction, and a mobile UA retry.
    """
    try:
        try:
            r = _get(url, ARTICLE_HEADERS, FULLTEXT_TIMEOUT)
        except Exception:
            mob = dict(ARTICLE_HEADERS); mob["User-Agent"] = MOBILE_UA
            r = _get(url, mob, FULLTEXT_TIMEOUT)

        html = r.text
        base = r.url
        soup = BeautifulSoup(html, "lxml")

        amp = soup.find("link", rel=lambda v: v and "amphtml" in v.lower())
        if amp and amp.get("href"):
            try:
                rr = _get(urljoin(base, amp["href"]), ARTICLE_HEADERS, FULLTEXT_TIMEOUT)
                html = rr.text
                base = rr.url
                soup = BeautifulSoup(html, "lxml")
            except Exception:
                pass

        # Text extraction
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

        # Image extraction
        img = None
        candidates = []

        for key, val in (("property","og:image"),
                         ("property","og:image:url"),
                         ("name","twitter:image"),
                         ("name","twitter:image:src")):
            for tag in soup.find_all("meta", attrs={key: val}):
                u = tag.get("content")
                if u: candidates.append(urljoin(base, u.strip()))

        for sel in [('link', {"rel":"image_src"}),
                    ('meta', {"itemprop":"image"}),
                    ('meta', {"name":"parsely-image"}),
                    ('meta', {"name":"thumbnail"})]:
            for tag in soup.find_all(sel[0], attrs=sel[1]):
                u = tag.get("href") or tag.get("content")
                if u: candidates.append(urljoin(base, u.strip()))

        candidates.extend(_jsonld_images(soup, base))

        for node in soup.find_all(["amp-img","img"]):
            u = _img_url_from_tag(node, base)
            if u: candidates.append(u)

        container = soup.find("article") or soup.find("main") or soup
        for img_tag in container.find_all("img"):
            u = _img_url_from_tag(img_tag, base)
            if u: candidates.append(u)

        seen, clean = set(), []
        for u in candidates:
            if not u or u in seen: 
                continue
            seen.add(u)
            if u.startswith("data:"): 
                continue
            if IMG_BAD_PAT.search(u): 
                continue
            clean.append(u)

        if clean:
            img = clean[0]

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

def dedupe_and_rank(items: List[Dict[str, Any]], top_k: int = 40) -> List[Dict[str, Any]]:
    now_ts = int(time.time())
    best: Dict[str, Dict[str, Any]] = {}
    for a in items:
        key = title_key(a.get("title","")) or _norm_url(a.get("url",""))
        a["score"] = score_item(a, now_ts)
        if key not in best or a["score"] > best[key]["score"]:
            best[key] = a
    return sorted(best.values(), key=lambda x: (x.get("score",0), x.get("published_ts") or 0), reverse=True)[:top_k]

# ----------------- Supabase -----------------
def article_id_for(url: str, title: str) -> str:
    base = _norm_url(url) or title
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def upsert_articles(rows: List[Dict[str, Any]], supabase_url: str, service_role: str) -> List[Dict[str, Any]]:
    if not rows:
        return []
    rest = f"{supabase_url}/rest/v1/news_articles?on_conflict=canonical_url"
    hdrs = {
        "apikey": service_role,
        "Authorization": f"Bearer {service_role}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    r = requests.post(rest, headers=hdrs, data=json.dumps(rows), timeout=60)
    r.raise_for_status()
    return r.json()

# ----------------- Runner (backfill) -----------------
def run_backfill(
    start_date: str,
    end_date: str,
    step_days: int | None = None,
    lang: str = "en-US",
    country: str = "US",
):
    window_days   = int(os.getenv("BACKFILL_STEP_DAYS", str(step_days or 10)))
    overlap_days  = int(os.getenv("BACKFILL_OVERLAP_DAYS", "2"))
    step_forward  = max(1, window_days - overlap_days)

    supabase_url  = SUPABASE_URL
    service_role  = SUPABASE_SERVICE_ROLE

    t0    = datetime.fromisoformat(start_date).date()
    t_end = datetime.fromisoformat(end_date).date()

    while t0 <= t_end:
        t1 = min(t0 + timedelta(days=window_days - 1), t_end)
        win_start, win_end = t0.isoformat(), t1.isoformat()

        # -------- fetch: general bucket for this window --------
        fetched_general: List[Dict[str, Any]] = []
        for q in QUERIES:
            fetched_general.extend(
                google_news_rss(
                    q=q, lang=lang, country=country, max_items=120,
                    start_date=win_start, end_date=win_end
                )
            )

        # -------- fetch: specific bucket (user search + tickers) --------
        fetched_specific: List[Dict[str, Any]] = []
        for q in build_specific_queries(USER_SEARCH, TICKERS_ENV):
            fetched_specific.extend(
                google_news_rss(
                    q=q, lang=lang, country=country, max_items=120,
                    start_date=win_start, end_date=win_end
                )
            )

        # fill "author" with publisher/outlet
        for a in (fetched_general + fetched_specific):
            if not a.get("author") and a.get("source"):
                a["author"] = a["source"]

        # choose and dedupe across buckets
        selected = pick_top_per_bucket(
            general_items=fetched_general,
            specific_items=fetched_specific,
            n_general=N_GENERAL,
            n_specific=N_SPECIFIC,
        )
        selected = _dedupe_articles(selected)

        # -------- fulltext + thumbnail --------
        for a in selected:
            needs_img = not _has_real_img(a)
            if not a.get("content") or needs_img:
                body, ogimg = fetch_article(a["url"])
                if body and not a.get("content"):
                    a["content"] = body
                if ogimg and needs_img:
                    a["image"] = ogimg

            if not a.get("content") and a.get("snippet"):
                snip = a["snippet"].strip()
                if snip:
                    a["content"] = snip

        selected = _dedupe_articles(selected)

        # -------- upsert rows --------
        rows: List[Dict[str, Any]] = []
        for a in selected:
            norm_url = _norm_url(a["url"])
            pub_dt = (
                datetime.fromtimestamp(a["published_ts"], tz=timezone.utc)
                if a.get("published_ts") else None
            )
            row = {
                "article_id"   : article_id_for(norm_url, a["title"]),
                "title"        : a["title"],
                "canonical_url": norm_url,
                "source"       : a.get("source"),
                "author"       : a.get("author"),
                "snippet"      : a.get("snippet"),
                "published_at" : pub_dt.isoformat() if pub_dt else None,
                "score"        : a.get("score"),
                "raw"          : None,
            }
            if a.get("content"):
                row["content"] = a["content"]
            if _has_real_img(a):
                row["image_url"] = a.get("image")
            rows.append(row)

        saved = upsert_articles(rows, supabase_url, service_role) if rows else []
        print(f"[backfill] {win_start} -> {win_end} : upserted {len(saved)}")

        t0 = t0 + timedelta(days=step_forward)

if __name__ == "__main__":
    missing = [k for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE") if not os.getenv(k)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)}")
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=365)).isoformat()
    # run_backfill(start_date=start, end_date=today.isoformat())
