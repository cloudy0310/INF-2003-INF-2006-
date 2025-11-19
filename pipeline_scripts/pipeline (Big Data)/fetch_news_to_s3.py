# fetch_news_to_s3.py
import os
import json
from datetime import datetime, timezone

import boto3

from fetch_news_all import (
    QUERIES,
    google_news_rss,
    build_specific_queries,
    _dedupe_articles,
    _has_real_img,
    fetch_article,
    N_GENERAL,
    N_SPECIFIC,
    USER_SEARCH,
    TICKERS_ENV,
    pick_top_per_bucket,
    article_id_for,
    _norm_url,
)

# --------- Config ---------
S3_BUCKET = os.getenv("NEWS_RAW_S3_BUCKET")          # e.g. cloud-project-stock-data
S3_PREFIX = os.getenv("NEWS_RAW_S3_PREFIX", "news_raw")

s3 = boto3.client("s3")


def collect_articles_for_day(target_date=None):
    """Reuse your existing logic to fetch + clean articles, no Supabase."""
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    start = target_date
    end = target_date

    # ---- general queries ----
    fetched_general = []
    for q in QUERIES:
        fetched_general.extend(
            google_news_rss(
                q=q,
                lang="en-US",
                country="US",
                max_items=120,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        )

    # ---- specific queries (tickers, custom terms) ----
    fetched_specific = []
    for q in build_specific_queries(USER_SEARCH, TICKERS_ENV):
        fetched_specific.extend(
            google_news_rss(
                q=q,
                lang="en-US",
                country="US",
                max_items=120,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        )

    # fill missing author with source
    for a in (fetched_general + fetched_specific):
        if not a.get("author") and a.get("source"):
            a["author"] = a["source"]

    # ---- choose + dedupe ----
    selected = pick_top_per_bucket(
        general_items=fetched_general,
        specific_items=fetched_specific,
        n_general=N_GENERAL,
        n_specific=N_SPECIFIC,
    )
    selected = _dedupe_articles(selected)

    # ---- enrich with full text + images ----
    for a in selected:
        needs_img = not _has_real_img(a)
        if not a.get("content") or needs_img:
            body, ogimg = fetch_article(a["url"])
            if body and not a.get("content"):
                a["content"] = body
            if ogimg and needs_img:
                a["image"] = ogimg
        # fallback: snippet as content
        if not a.get("content") and a.get("snippet"):
            a["content"] = a["snippet"].strip()

    selected = _dedupe_articles(selected)

    # ---- final rows ----
    rows = []
    for a in selected:
        norm_url = _norm_url(a["url"])
        pub_ts = a.get("published_ts")
        if pub_ts:
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
            pub_iso = pub_dt.isoformat()
        else:
            pub_iso = None

        rows.append(
            {
                "article_id": article_id_for(norm_url, a["title"]),
                "title": a["title"],
                "canonical_url": norm_url,
                "source": a.get("source"),
                "author": a.get("author"),
                "snippet": a.get("snippet"),
                "content": a.get("content"),
                "image_url": a.get("image") if _has_real_img(a) else None,
                "published_at": pub_iso,
                "score": a.get("score"),
            }
        )

    return rows


def save_articles_to_s3(rows, target_date=None):
    """Save list of articles as JSONL to S3."""
    if not rows:
        print("No articles to save; skipping S3 upload.")
        return

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


if __name__ == "__main__":
    if not S3_BUCKET:
        raise SystemExit(
            "Missing env var NEWS_RAW_S3_BUCKET. "
            "Set it to your S3 bucket name before running."
        )

    today = datetime.now(timezone.utc).date()
    print(f"Collecting news for {today}...")
    articles = collect_articles_for_day(today)
    print(f"Fetched {len(articles)} articles.")
    save_articles_to_s3(articles, today)
