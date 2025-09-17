from __future__ import annotations
from typing import List, Dict, Any, Optional
from supabase import Client

def _apply_filters(q, ticker: Optional[str], tags_any: Optional[list[str]],
                   search: Optional[str], only_published: bool):
    if only_published:
        q = q.not_.is_("published_at", None)
    if ticker:
        q = q.eq("ticker", ticker.upper().strip())
    if tags_any:
        q = q.overlaps("tags", tags_any)
    if search:
        like = f"%{search}%"
        q = q.or_(f"title.ilike.{like},excerpt.ilike.{like}")
    return q

def list_content(
    sb: Client,
    page: int = 1,
    page_size: int = 12,
    ticker: Optional[str] = None,
    tags_any: Optional[list[str]] = None,
    search: Optional[str] = None,
    only_published: bool = True,
) -> List[Dict[str, Any]]:
    start = max(0, (page - 1) * page_size)
    end = start + page_size - 1
    q = sb.table("content").select(
        "id,title,slug,excerpt,image_url,tags,published_at,content_type,ticker"
    ).order("published_at", desc=True)
    q = _apply_filters(q, ticker, tags_any, search, only_published)
    res = q.range(start, end).execute()
    return res.data or []

def count_content(
    sb: Client,
    ticker: Optional[str] = None,
    tags_any: Optional[list[str]] = None,
    search: Optional[str] = None,
    only_published: bool = True,
) -> int:
    q = sb.table("content").select("id", count="exact")
    q = _apply_filters(q, ticker, tags_any, search, only_published)
    res = q.execute()
    return int(getattr(res, "count", 0) or 0)
