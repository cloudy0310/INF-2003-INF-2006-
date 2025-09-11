import time, urllib.parse
from typing import List, Optional
import feedparser
from bs4 import BeautifulSoup
from .news_sources import Article, normalize_source

def _parse_item(entry) -> Article:
    title = entry.get("title", "")
    link  = entry.get("link", "")
    published_ts = int(time.mktime(entry.published_parsed)) if entry.get("published_parsed") else None
    source = normalize_source(entry.source.get("title")) if entry.get("source") else None
    snippet = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True) or None
    image = None
    media = entry.get("media_content") or entry.get("media_thumbnail")
    if isinstance(media, list) and media and media[0].get("url"):
        image = media[0]["url"]
    return Article(title, link, published_ts, source, snippet, image, entry)

def google_news_rss(q: Optional[str]=None, lang="en-US", country="US", max_items=60) -> List[Article]:
    base = "https://news.google.com/rss"
    if q:
        url = f"{base}/search?q={urllib.parse.quote(q)}&hl={lang}&gl={country}&ceid={country}:{lang}"
    else:
        url = f"{base}?hl={lang}&gl={country}&ceid={country}:{lang}"
    feed = feedparser.parse(url)
    return [_parse_item(e) for e in feed.entries[:max_items]]
