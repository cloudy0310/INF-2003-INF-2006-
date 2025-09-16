# app/api/content.py
import os
import json
from typing import Optional, Dict, Any
from supabase import create_client

# ---------- Supabase helpers ----------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE")


def supabase_client():
    if create_client is None or SUPABASE_URL is None or SUPABASE_KEY is None:
        raise RuntimeError("Supabase client not configured. Set SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE).")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------- CRUD wrappers ----------
def list_content(supabase, published_only: bool = False, limit: Optional[int] = None, offset: Optional[int] = None, tag: Optional[str] = None, ticker: Optional[str] = None) -> Dict[str, Any]:
    """Return list of content records. Returns dict with keys: data, error"""
    try:
        qb = supabase.table("content").select("*")
        if published_only:
            # not all clients support .is_, so we'll rely on server-side if possible; otherwise filter in Python below
            try:
                qb = qb.is_("published_at", "not", None)
            except Exception:
                pass
        if ticker:
            qb = qb.eq("ticker", ticker)
        if limit:
            qb = qb.limit(limit)
        if offset and limit:
            qb = qb.range(offset, offset + limit - 1)
        res = qb.order("published_at", desc=True).execute()
        if hasattr(res, "data"):
            data = res.data
            err = res.error if hasattr(res, "error") else None
        elif isinstance(res, dict):
            data = res.get("data")
            err = res.get("error")
        else:
            data, err = None, None
        # fallback filter by tag
        if tag and data:
            data = [d for d in data if tag in (d.get("tags") or [])]
        if published_only and data:
            data = [d for d in data if d.get("published_at")]
        return {"data": data, "error": err}
    except Exception as e:
        return {"data": None, "error": str(e)}


def get_content(supabase, id: Optional[str] = None, slug: Optional[str] = None) -> Dict[str, Any]:
    try:
        if id:
            res = supabase.table("content").select("*").eq("id", id).single().execute()
        elif slug:
            res = supabase.table("content").select("*").eq("slug", slug).single().execute()
        else:
            return {"data": None, "error": "id or slug required"}
        if hasattr(res, "data"):
            return {"data": res.data, "error": res.error if hasattr(res, "error") else None}
        if isinstance(res, dict):
            return {"data": res.get("data"), "error": res.get("error")}
        return {"data": None, "error": None}
    except Exception as e:
        return {"data": None, "error": str(e)}


def create_content(supabase, payload) -> Dict[str, Any]:
    try:
        res = supabase.table("content").insert(payload).execute()
        if hasattr(res, "data"):
            return {"data": res.data, "error": res.error if hasattr(res, "error") else None}
        if isinstance(res, dict):
            return {"data": res.get("data"), "error": res.get("error")}
        return {"data": None, "error": None}
    except Exception as e:
        return {"data": None, "error": str(e)}


def update_content(supabase, content_id: str, payload) -> Dict[str, Any]:
    try:
        res = supabase.table("content").update(payload).eq("id", content_id).execute()
        if hasattr(res, "data"):
            return {"data": res.data, "error": res.error if hasattr(res, "error") else None}
        if isinstance(res, dict):
            return {"data": res.get("data"), "error": res.get("error")}
        return {"data": None, "error": None}
    except Exception as e:
        return {"data": None, "error": str(e)}


def delete_content(supabase, content_id: str) -> Dict[str, Any]:
    try:
        res = supabase.table("content").delete().eq("id", content_id).execute()
        if hasattr(res, "data"):
            return {"data": res.data, "error": res.error if hasattr(res, "error") else None}
        if isinstance(res, dict):
            return {"data": res.get("data"), "error": res.get("error")}
        return {"data": None, "error": None}
    except Exception as e:
        return {"data": None, "error": str(e)}