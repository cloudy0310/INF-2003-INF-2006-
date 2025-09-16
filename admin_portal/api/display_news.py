# app/api/display_news.py
from __future__ import annotations
import os
import requests
from datetime import date
from typing import Optional, List, Dict
from dotenv import load_dotenv, find_dotenv

# Load root .env (SUPABASE_URL, SUPABASE_ANON_KEY)
load_dotenv(find_dotenv())

SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY env vars")

REST = f"{SUPABASE_URL}/rest/v1"
HDRS = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"}

def list_news(
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    page: int = 1,
) -> List[Dict]:
    """
    Read-only fetch from news_articles with filters and pagination.
    """
    assert page >= 1
    offset = (page - 1) * limit

    params = {
        "select": "*",
        "order": "published_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }

    # Date range filter (PostgREST AND)
    and_clauses = []
    if start_iso:
        and_clauses.append(f"published_at.gte.{start_iso}")
    if end_iso:
        and_clauses.append(f"published_at.lte.{end_iso}")
    if and_clauses:
        params["and"] = f"({','.join(and_clauses)})"

    # Source exact match
    if source:
        params["source"] = f"eq.{source}"

    # Simple search across title/snippet
    if q:
        params["or"] = f"(title.ilike.*{q}*,snippet.ilike.*{q}*)"

    r = requests.get(f"{REST}/news_articles", headers=HDRS, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def get_daily_summary(day: date) -> Optional[Dict]:
    params = {"day": f"eq.{day.isoformat()}"}
    r = requests.get(f"{REST}/news_daily_summary", headers=HDRS, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None
