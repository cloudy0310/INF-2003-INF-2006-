import os
import json
import argparse
from datetime import datetime, timezone, timedelta

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, desc

import urllib.request as urlrequest
import urllib.error as urlerror


# ------- Config from env (with safe defaults) -------
S3_BUCKET = os.getenv("NEWS_RAW_S3_BUCKET", "cloud-project-stock-data")
RAW_PREFIX = os.getenv("NEWS_RAW_S3_PREFIX", "news_raw")
SUMMARY_PREFIX = os.getenv("NEWS_SUMMARY_S3_PREFIX", "news_summaries")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # <-- set via EMR step env
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DEFAULT_MAX_ARTS = int(os.getenv("SUMMARY_MAX_ARTS", "10"))
DEFAULT_RECENT_HOURS = int(os.getenv("SUMMARY_RECENT_HOURS", "36"))


def fetch_articles_df(spark: SparkSession, date_str: str):
    """
    Load the raw articles JSONL for a given dt=YYYY-MM-DD partition.
    """
    input_path = f"s3://{S3_BUCKET}/{RAW_PREFIX}/dt={date_str}/articles.jsonl"
    print(f"[INFO] Reading articles from {input_path}")
    df = spark.read.json(input_path)
    return df


def select_recent_articles(df, max_articles: int, recent_hours: int, now_utc=None):
    """
    Filter to articles whose published_at is within recent_hours of now and
    return at most max_articles of them, newest first.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    cutoff = now_utc - timedelta(hours=recent_hours)
    cutoff_str = cutoff.isoformat()
    print(f"[INFO] Selecting articles published after {cutoff_str}")

    # Convert published_at ISO strings to timestamp
    df2 = df.withColumn("published_ts", to_timestamp(col("published_at")))

    # Filter by recent hours and sort newest first
    filtered = (
        df2.filter(col("published_ts") >= cutoff_str)
           .orderBy(desc("published_ts"))
           .limit(max_articles)
    )

    articles = filtered.select(
        "article_id", "title", "canonical_url",
        "source", "snippet", "content", "published_at"
    ).collect()

    result = [row.asDict() for row in articles]
    print(f"[INFO] select_recent_articles: {len(result)} rows after filtering")
    return result


def build_gemini_prompt(articles):
    """
    Construct a single long prompt for Gemini from the selected articles.
    """
    lines = [
        "You are a financial news analyst.",
        "Summarise the following articles into a concise market summary.",
        "Focus on:",
        "- Overall market direction and macro themes",
        "- Sector or asset-class moves",
        "- Notable company-specific stories",
        "",
        "Write in 3–6 paragraphs, plain text, no bullet points.",
        "",
        "Articles:",
        "---------",
    ]
    for i, a in enumerate(articles, start=1):
        title = a.get("title") or ""
        src = a.get("source") or ""
        url = a.get("canonical_url") or ""
        pub = a.get("published_at") or ""
        snippet = (a.get("snippet") or "")[:1000]
        content = (a.get("content") or "")[:1500]

        lines.append(f"[{i}] {title}")
        if src or pub:
            lines.append(f"Source: {src} | Time: {pub}")
        if url:
            lines.append(f"URL: {url}")
        if content:
            lines.append(f"Content: {content}")
        elif snippet:
            lines.append(f"Snippet: {snippet}")
        lines.append("")  # blank line between articles

    lines.append("Now provide a cohesive narrative summary as requested above.")
    return "\n".join(lines)


def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    url = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    # Simple, valid v1 payload (no systemInstruction)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192
        }
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"[INFO] Calling Gemini model={GEMINI_MODEL}")

    try:
        with urlrequest.urlopen(req, timeout=60) as resp:
            status = resp.getcode()
            resp_body = resp.read().decode("utf-8")
            print(f"[INFO] Gemini HTTP {status}")
    except urlerror.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="ignore")
        except Exception:
            err_body = "<no body>"
        raise RuntimeError(f"Gemini HTTPError {e.code}: {err_body}") from e
    except urlerror.URLError as e:
        raise RuntimeError(f"Gemini connection error: {e}") from e

    # Parse JSON
    try:
        data = json.loads(resp_body)
    except json.JSONDecodeError:
        raise RuntimeError(f"Failed to parse Gemini JSON: {resp_body}")

    # Safely extract text
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"No candidates returned from Gemini: {data}")

    first = candidates[0]
    content = first.get("content") or {}
    parts = content.get("parts") or []

    if not parts:
        finish = first.get("finishReason")
        usage = data.get("usageMetadata")
        raise RuntimeError(
            f"Model returned no text parts (finishReason={finish}, usage={usage}). "
            f"Full response: {data}"
        )

    text = parts[0].get("text", "").strip()
    if not text:
        raise RuntimeError(f"Empty text in first part: {data}")

    return text




def save_summary_to_s3(summary_text: str, date_str: str, used_articles):
    """
    Save the generated summary plus metadata back to S3 as JSON.
    """
    key = f"{SUMMARY_PREFIX}/dt={date_str}/summary.json"

    body = {
        "date": date_str,
        "article_count": len(used_articles),
        "summary": summary_text,
        "articles": used_articles,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": GEMINI_MODEL,
    }

    import boto3
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"[INFO] Saved summary to s3://{S3_BUCKET}/{key}")
    return key


def main(date_str: str, max_articles: int, recent_hours: int):
    spark = (
        SparkSession.builder
        .appName(f"NewsSummary-{date_str}")
        .getOrCreate()
    )

    try:
        df = fetch_articles_df(spark, date_str)
        articles = select_recent_articles(df, max_articles, recent_hours)

        if not articles:
            print("[INFO] No recent articles found; nothing to summarise.")
            return

        print(f"[INFO] Selected {len(articles)} articles for summarisation.")

        prompt = build_gemini_prompt(articles)
        summary = call_gemini(prompt)
        save_summary_to_s3(summary, date_str, articles)
    finally:
        # Ensure Spark shuts down even if something raises
        spark.stop()
        print("[INFO] Spark session stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (same as S3 dt=...)")
    parser.add_argument("--max_articles", type=int, default=DEFAULT_MAX_ARTS)
    parser.add_argument("--recent_hours", type=int, default=DEFAULT_RECENT_HOURS)
    args = parser.parse_args()

    print(
        f"[INFO] Starting with date={args.date}, "
        f"max_articles={args.max_articles}, recent_hours={args.recent_hours}"
    )
    print(
        f"[INFO] Config S3_BUCKET={S3_BUCKET}, RAW_PREFIX={RAW_PREFIX}, "
        f"SUMMARY_PREFIX={SUMMARY_PREFIX}, GEMINI_MODEL={GEMINI_MODEL}"
    )

    main(args.date, args.max_articles, args.recent_hours)
