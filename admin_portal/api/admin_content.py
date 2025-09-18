# api/admin_content.py  (RDS/Postgres version)
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from sqlalchemy import text, String, bindparam
from sqlalchemy.engine import Engine, Result
from sqlalchemy.dialects.postgresql import ARRAY

# ---------- Helpers ----------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _csv_to_tags(csv_or_list: Optional[Any]) -> List[str]:
    if csv_or_list is None:
        return []
    if isinstance(csv_or_list, list):
        return [str(t).strip() for t in csv_or_list if str(t).strip()]
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

def _build_admin_where(
    *,
    search: Optional[str],
    ticker: Optional[str],
    content_type: Optional[str],
    status: str,  # all | published | drafts
) -> Tuple[str, Dict[str, Any]]:
    clauses = []
    params: Dict[str, Any] = {}

    if search:
        clauses.append("(title ILIKE :search OR excerpt ILIKE :search OR slug ILIKE :search)")
        params["search"] = f"%{search}%"

    if ticker:
        clauses.append("ticker = :ticker")
        params["ticker"] = ticker.upper().strip()

    if content_type:
        clauses.append("content_type = :content_type")
        params["content_type"] = content_type

    if status == "published":
        clauses.append("published_at IS NOT NULL")
    elif status == "drafts":
        clauses.append("published_at IS NULL")

    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    return where_sql, params

# ---------- List / Count / Get ----------
def admin_list_content(
    rds: Engine,
    *,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    ticker: Optional[str] = None,
    content_type: Optional[str] = None,
    status: str = "all",  # all | published | drafts
) -> List[Dict[str, Any]]:
    """
    Admin list with optional filters. Includes drafts when status='all' or 'drafts'.
    Ordered by created_at DESC.
    """
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    offset = (page - 1) * page_size

    where_sql, params = _build_admin_where(
        search=search, ticker=ticker, content_type=content_type, status=status
    )

    sql = text(f"""
        SELECT
            id, author_id, title, slug, excerpt, image_url, ticker, tags, content_type,
            published_at, created_at, updated_at, body, raw_meta
        FROM public.content
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    with rds.connect() as conn:
        res: Result = conn.execute(sql, {**params, "limit": page_size, "offset": offset})
        return [dict(row) for row in res.mappings().all()]

def admin_count_content(
    rds: Engine,
    *,
    search: Optional[str] = None,
    ticker: Optional[str] = None,
    content_type: Optional[str] = None,
    status: str = "all",
) -> int:
    where_sql, params = _build_admin_where(
        search=search, ticker=ticker, content_type=content_type, status=status
    )

    sql = text(f"""
        SELECT COUNT(*) AS cnt
        FROM public.content
        WHERE {where_sql}
    """)

    with rds.connect() as conn:
        res: Result = conn.execute(sql, params)
        row = res.first()
        return int(row[0]) if row else 0

def admin_get_content(rds: Engine, content_id: str) -> Optional[Dict[str, Any]]:
    sql = text("""
        SELECT *
        FROM public.content
        WHERE id = :id
        LIMIT 1
    """)
    with rds.connect() as conn:
        res: Result = conn.execute(sql, {"id": content_id})
        row = res.mappings().first()
        return dict(row) if row else None

# ---------- Create / Update / Delete ----------
def admin_create_content(
    rds: Engine,
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
    tags_list = _csv_to_tags(tags)
    slug_val = _ensure_slug(slug, title)

    # Use DB clock for published_at when requested
    published_expr = "now()" if publish_now else "NULL"

    sql = text(f"""
        INSERT INTO public.content
            (author_id, title, slug, body, excerpt, image_url, ticker, tags, content_type, raw_meta, published_at)
        VALUES
            (:author_id, :title, :slug, :body, :excerpt, :image_url, :ticker, :tags, :content_type, :raw_meta, {published_expr})
        RETURNING
            id, author_id, title, slug, body, excerpt, image_url, ticker, tags, content_type,
            published_at, created_at, updated_at, raw_meta
    """)

    params = {
        "author_id": author_id,
        "title": title.strip(),
        "slug": slug_val,
        "body": body or "",
        "excerpt": (excerpt or "").strip() or None,
        "image_url": (image_url or "").strip() or None,
        "ticker": (ticker or "").upper().strip() or None,
        # Explicit ARRAY(String) bind so psycopg2 sends text[]
        "tags": bindparam("tags", value=tags_list, type_=ARRAY(String)),
        "content_type": content_type or "analysis",
        "raw_meta": None,
    }

    with rds.connect() as conn:
        res: Result = conn.execute(sql, params)
        row = res.mappings().first()
        return dict(row) if row else {
            **{k: (v.value if hasattr(v, "value") else v) for k, v in params.items()},
            "published_at": _now_iso() if publish_now else None,
        }

def admin_update_content(
    rds: Engine,
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
    # Build dynamic SET list
    sets: List[str] = []
    params: Dict[str, Any] = {"id": content_id}

    if title is not None:
        sets.append("title = :title")
        params["title"] = title.strip()
    if body is not None:
        sets.append("body = :body")
        params["body"] = body
    if slug is not None:
        sets.append("slug = :slug")
        params["slug"] = _ensure_slug(slug, title)
    if excerpt is not None:
        sets.append("excerpt = :excerpt")
        params["excerpt"] = (excerpt or "").strip() or None
    if image_url is not None:
        sets.append("image_url = :image_url")
        params["image_url"] = (image_url or "").strip() or None
    if ticker is not None:
        sets.append("ticker = :ticker")
        params["ticker"] = (ticker or "").upper().strip() or None
    if tags is not None:
        sets.append("tags = :tags")
        params["tags"] = bindparam("tags", value=_csv_to_tags(tags), type_=ARRAY(String))
    if content_type is not None:
        sets.append("content_type = :content_type")
        params["content_type"] = content_type

    if publish_now is True:
        sets.append("published_at = now()")
    if unpublish is True:
        sets.append("published_at = NULL")

    if not sets:
        # Nothing to update; return the current row if present
        current = admin_get_content(rds, content_id)
        return current or {"id": content_id}

    set_sql = ", ".join(sets)
    sql = text(f"""
        UPDATE public.content
        SET {set_sql}, updated_at = now()
        WHERE id = :id
        RETURNING
            id, author_id, title, slug, body, excerpt, image_url, ticker, tags, content_type,
            published_at, created_at, updated_at, raw_meta
    """)

    with rds.connect() as conn:
        res: Result = conn.execute(sql, params)
        row = res.mappings().first()
        return dict(row) if row else {"id": content_id, **{k: (v.value if hasattr(v, "value") else v) for k, v in params.items()}}

def admin_delete_content(rds: Engine, content_id: str) -> None:
    sql = text("DELETE FROM public.content WHERE id = :id")
    with rds.connect() as conn:
        conn.execute(sql, {"id": content_id})
