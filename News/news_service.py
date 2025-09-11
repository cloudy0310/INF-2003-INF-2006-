from typing import List, Dict
from datetime import datetime, timedelta, timezone
from .rss_client import google_news_rss
from .ranker import dedupe_and_rank

def top_market_news_today(lang="en-US", country="US", top_k=10) -> List[Dict]:
    queries = [
        'stock market OR equities OR "S&P 500" OR Dow OR Nasdaq',
        'markets today OR premarket OR futures',
        'earnings OR guidance'
    ]
    items = []
    for q in queries:
        items.extend(google_news_rss(q=q, lang=lang, country=country, max_items=60))
    ranked = dedupe_and_rank(items, top_k=top_k)
    return [_payload(a, s) for a, s in ranked]

def top_ticker_news_last_month(ticker: str, company_name: str = "", lang="en-US", country="US", top_k=10) -> List[Dict]:
    base_q = f'"{ticker}"'
    if company_name and company_name.lower() not in ticker.lower():
        base_q += f' OR "{company_name}"'
    q = f'({base_q}) (stock OR shares OR earnings OR guidance OR revenue OR SEC)'
    items = google_news_rss(q=q, lang=lang, country=country, max_items=80)

    cutoff = datetime.now(timezone.utc) - timedelta(days=31)
    filt = [a for a in items if (a.published_ts and datetime.fromtimestamp(a.published_ts, tz=timezone.utc) >= cutoff)]
    ranked = dedupe_and_rank(filt, top_k=top_k)
    return [_payload(a, s) for a, s in ranked]

def _payload(a, score) -> Dict:
    return {
        "title": a.title, "url": a.link, "source": a.source,
        "published_ts": a.published_ts, "snippet": a.snippet,
        "image": a.image, "score": round(score, 3)
    }
