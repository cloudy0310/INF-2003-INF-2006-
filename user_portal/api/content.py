# api/content.py
from __future__ import annotations
from typing import List, Optional
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine, Result
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import String, bindparam

# Helper to build WHERE clauses consistently
def _where_clauses(
    only_published: bool,
    ticker: Optional[str],
    tags_any: Optional[List[str]],
    search: Optional[str],
):
    clauses = []
    bind_params = {}

    if only_published:
        clauses.append("published_at IS NOT NULL AND published_at <= now()")

    if ticker:
        clauses.append("ticker = :ticker")
        bind_params["ticker"] = ticker

    if tags_any:
        # Overlap operator: tags && <array>
        clauses.append("tags && :tags_any")
        # Bind with an explicit ARRAY(String) so psycopg2 sends a text[]
        bind_params["tags_any"] = bindparam("tags_any", value=tags_any, type_=ARRAY(String))

    if search:
        clauses.append("(title ILIKE '%' || :search || '%' OR excerpt ILIKE '%' || :search || '%')")
        bind_params["search"] = search

    if not clauses:
        where_sql = "TRUE"
    else:
        where_sql = " AND ".join(clauses)

    return where_sql, bind_params

def count_content(
    rds: Engine,
    *,
    ticker: Optional[str] = None,
    tags_any: Optional[List[str]] = None,
    search: Optional[str] = None,
    only_published: bool = False,
) -> int:
    """
    Return number of rows in public.content matching filters.
    """
    where_sql, bind_params = _where_clauses(only_published, ticker, tags_any, search)
    sql = text(f"""
        SELECT COUNT(*) AS cnt
        FROM public.content
        WHERE {where_sql}
    """)

    # Extract values from bind_params for .execute()
    exec_params = {}
    for k, v in bind_params.items():
        # bindparam objects need .value for immediate execution
        exec_params[k] = getattr(v, "value", v)

    with rds.connect() as conn:
        res: Result = conn.execute(sql, exec_params)
        row = res.first()
        return int(row[0]) if row else 0

def list_content(
    rds: Engine,
    *,
    page: int = 1,
    page_size: int = 12,
    ticker: Optional[str] = None,
    tags_any: Optional[List[str]] = None,
    search: Optional[str] = None,
    only_published: bool = False,
):
    """
    Return list of dict rows from public.content matching filters, ordered by published_at DESC NULLS LAST,
    then created_at DESC. Supports pagination via page/page_size.
    """
    # Safety on pagination inputs
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))  # hard cap to prevent giant pulls
    offset = (page - 1) * page_size

    where_sql, bind_params = _where_clauses(only_published, ticker, tags_any, search)

    sql = text(f"""
        SELECT
            id, author_id, title, slug, body, excerpt, image_url, ticker, tags,
            published_at, created_at, updated_at, raw_meta, content_type
        FROM public.content
        WHERE {where_sql}
        ORDER BY published_at DESC NULLS LAST, created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    exec_params = {"limit": page_size, "offset": offset}
    for k, v in bind_params.items():
        exec_params[k] = getattr(v, "value", v)

    with rds.connect() as conn:
        res: Result = conn.execute(sql, exec_params)
        # result.mappings() gives dict-like rows
        return [dict(row) for row in res.mappings().all()]
