import json
import os
import hashlib
from datetime import datetime, timezone
from urllib import request, parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import boto3

# Environment variables (already set)
S3_BUCKET = os.getenv("NEWS_RAW_S3_BUCKET", "cloud-project-stock-data")
S3_PREFIX = os.getenv("NEWS_RAW_S3_PREFIX", "news_raw")

s3 = boto3.client("s3")

# A few sample queries – you can tweak these
QUERIES = [
    "stock market",
    "S&P 500",
    "Nasdaq",
    "interest rates",
]

MAX_ITEMS_PER_QUERY = 10  # to keep it light for Lambda


def google_news_rss(query: str, hl: str = "en-US", gl: str = "US", ceid: str = "US:en"):
    """
    Fetch Google News RSS results for a query using only stdlib.
    Returns a list of dicts with title, link, pubDate, description.
    """
    url = (
        "https://news.google.com/rss/search?"
        + parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    )

    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=10) as resp:
        data = resp.read()

    root = ET.fromstring(data)

    ns = {}  # RSS here is simple, no namespaces needed
    items = []
    for item in root.findall(".//item", ns)[:MAX_ITEMS_PER_QUERY]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub_raw = item.findtext("pubDate")
        pub_iso = None
        if pub_raw:
            try:
                dt = parsedate_to_datetime(pub_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                pub_iso = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pub_iso = None

        if not title or not link:
            continue

        items.append(
            {
                "title": title,
                "link": link,
                "snippet": desc,
                "published_at": pub_iso,
            }
        )
    return items


def build_articles():
    """
    Run all queries, dedupe by link, and return article dicts ready for JSONL.
    """
    seen_links = set()
    articles = []

    for q in QUERIES:
        rss_items = google_news_rss(q)
        for it in rss_items:
            link = it["link"]
            if link in seen_links:
                continue
            seen_links.add(link)

            # simple deterministic ID from link
            art_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

            articles.append(
                {
                    "article_id": art_id,
                    "title": it["title"],
                    "canonical_url": link,
                    "source": "Google News",
                    "author": None,
                    "snippet": it["snippet"],
                    "content": None,
                    "image_url": None,
                    "published_at": it["published_at"],
                    "score": None,
                    "raw": None,
                }
            )
    return articles


def save_articles_to_s3(rows, target_date=None):
    """
    Save list of article dicts as JSONL to S3:
    s3://<bucket>/<prefix>/dt=YYYY-MM-DD/articles.jsonl
    """
    if not rows:
        print("No articles to save; skipping S3 upload.")
        return None

    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    date_str = target_date.strftime("%Y-%m-%d")
    key = f"{S3_PREFIX}/dt={date_str}/articles.jsonl"

    body_lines = [json.dumps(r, default=str) for r in rows]
    body = "\n".join(body_lines)

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )

    print(f"Saved {len(rows)} articles to s3://{S3_BUCKET}/{key}")
    return key


def lambda_handler(event, context):
    today = datetime.now(timezone.utc).date()
    print(f"Collecting news for {today}...")

    articles = build_articles()
    print(f"Fetched {len(articles)} unique articles.")

    key = save_articles_to_s3(articles, today)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "date": today.isoformat(),
                "article_count": len(articles),
                "s3_key": key,
            }
        ),
    }
