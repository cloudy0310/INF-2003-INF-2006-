# api/admin_content.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from supabase import Client

# ---------- Helpers ----------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _csv_to_tags(csv_or_list: Optional[Any]) -> List[str]:
    if csv_or_list is None:
        return []
    if isinstance(csv_or_list, list):
        return [str(t).strip() for t in csv_or_list if str(t).strip()]
    # CSV string
    return [t.strip() for t in str(csv_or_list).split(",") if t.strip()]

def _ensure_slug(s: Optional[str], fallback_title: Optional[str]) -> Optional[str]:
    if s and s.strip():
        return (
            s.strip()
             .lower()
             .replace(" ", "-")
             .replace("--", "-")
        )
    if not fallback_title:
        return None
    base = fallback_title.strip().lower()
    out = []
    for ch in base:
        if ch.isalnum():
            out.append(ch)
        elif ch.isspace() or ch in "-_":
            out.append("-")
    slug = "".join(out).strip("-").replace("--", "-")
    return slug or None

# ---------- List / Count / Get ----------
def admin_list_content(
    sb: Client,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    ticker: Optional[str] = None,
    content_type: Optional[str] = None,
    status: str = "all",  # all | published | drafts
) -> List[Dict[str, Any]]:
    """
    Admin list with optional filters. Includes drafts (published_at NULL) when status='all' or 'drafts'.
    """
    start = max(0, (page - 1) * page_size)
    end = start + page_size - 1

    q = sb.table("content").select(
        "id, author_id, title, slug, excerpt, image_url, ticker, tags, content_type, "
        "published_at, created_at, updated_at, body"
    ).order("created_at", desc=True)

    if search:
        like = f"%{search}%"
        q = q.or_(f"title.ilike.{like},excerpt.ilike.{like},slug.ilike.{like}")
    if ticker:
        q = q.eq("ticker", ticker.upper().strip())
    if content_type:
        q = q.eq("content_type", content_type)
    if status == "published":
        q = q.not_.is_("published_at", None)
    elif status == "drafts":
        q = q.is_("published_at", None)

    res = q.range(start, end).execute()
    return res.data or []

def admin_count_content(
    sb: Client,
    search: Optional[str] = None,
    ticker: Optional[str] = None,
    content_type: Optional[str] = None,
    status: str = "all",
) -> int:
    q = sb.table("content").select("id", count="exact")
    if search:
        like = f"%{search}%"
        q = q.or_(f"title.ilike.{like},excerpt.ilike.{like},slug.ilike.{like}")
    if ticker:
        q = q.eq("ticker", ticker.upper().strip())
    if content_type:
        q = q.eq("content_type", content_type)
    if status == "published":
        q = q.not_.is_("published_at", None)
    elif status == "drafts":
        q = q.is_("published_at", None)
    res = q.execute()
    return int(getattr(res, "count", 0) or 0)

def admin_get_content(sb: Client, content_id: str) -> Optional[Dict[str, Any]]:
    res = sb.table("content").select("*").eq("id", content_id).single().execute()
    return res.data if getattr(res, "data", None) else None

# ---------- Create / Update / Delete ----------
def admin_create_content(
    sb: Client,
    *,
    title: str,
    body: str,
    author_id: Optional[str] = None,
    slug: Optional[str] = None,
    excerpt: Optional[str] = None,
    image_url: Optional[str] = None,
    ticker: Optional[str] = None,
    tags: Optional[List[str] | str] = None,
    content_type: Optional[str] = "analysis",
    publish_now: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "author_id": author_id,
        "title": title.strip(),
        "slug": _ensure_slug(slug, title),
        "body": body or "",
        "excerpt": (excerpt or "").strip() or None,
        "image_url": (image_url or "").strip() or None,
        "ticker": (ticker or "").upper().strip() or None,
        "tags": _csv_to_tags(tags),
        "content_type": content_type or "analysis",
        "raw_meta": None,
    }
    if publish_now:
        payload["published_at"] = _now_iso()

    res = sb.table("content").insert(payload).select("*").single().execute()
    return res.data

def admin_update_content(
    sb: Client,
    content_id: str,
    *,
    title: Optional[str] = None,
    body: Optional[str] = None,
    slug: Optional[str] = None,
    excerpt: Optional[str] = None,
    image_url: Optional[str] = None,
    ticker: Optional[str] = None,
    tags: Optional[List[str] | str] = None,
    content_type: Optional[str] = None,
    publish_now: Optional[bool] = None,
    unpublish: Optional[bool] = None,
) -> Dict[str, Any]:
    upd: Dict[str, Any] = {}
    if title is not None: upd["title"] = title.strip()
    if body is not None: upd["body"] = body
    if slug is not None: upd["slug"] = _ensure_slug(slug, title)
    if excerpt is not None: upd["excerpt"] = excerpt.strip() or None
    if image_url is not None: upd["image_url"] = image_url.strip() or None
    if ticker is not None: upd["ticker"] = ticker.upper().strip() or None
    if tags is not None: upd["tags"] = _csv_to_tags(tags)
    if content_type is not None: upd["content_type"] = content_type

    if publish_now is True:
        upd["published_at"] = _now_iso()
    if unpublish is True:
        upd["published_at"] = None

    res = sb.table("content").update(upd).eq("id", content_id).select("*").single().execute()
    return res.data

def admin_delete_content(sb: Client, content_id: str) -> None:
    sb.table("content").delete().eq("id", content_id).execute()
