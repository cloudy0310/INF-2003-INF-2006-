# api/watchlist.py
"""
Watchlist helpers that interact with Supabase.
Functions:
- add_to_watchlist(user_id: str, ticker: str) -> dict
- get_watchlist_count(ticker: str) -> int

Environment:
  SUPABASE_URL, SUPABASE_KEY must be set.
"""
import os
from supabase import create_client
from typing import Optional

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    # Fail fast when module imported in environments without config.
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in environment variables for watchlist.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def add_to_watchlist(user_id: str, ticker: str, watchlist_name: Optional[str] = "default") -> dict:
    """
    Add a ticker to the user's watchlist (creates default watchlist if not found).
    Returns dict with status and watchlist_id.
    """
    ticker = ticker.upper()
    # Find existing default watchlist
    res = supabase.table("watchlists").select("*").eq("user_id", user_id).eq("name", watchlist_name).limit(1).execute()
    if res.error:
        raise RuntimeError(f"Supabase error: {res.error}")
    if res.data:
        watchlist_id = res.data[0]["watchlist_id"]
    else:
        create = supabase.table("watchlists").insert({
            "user_id": user_id,
            "name": watchlist_name,
            "description": "Default watchlist"
        }).execute()
        if create.error:
            raise RuntimeError(f"Failed to create watchlist: {create.error}")
        watchlist_id = create.data[0]["watchlist_id"]

    # Insert into watchlist_stocks; if duplicate, supabase will likely error -> ignore duplicates
    insert = supabase.table("watchlist_stocks").insert({
        "watchlist_id": watchlist_id,
        "ticker": ticker
    }).execute()

    if insert.error:
        # tolerate unique constraint errors / duplicates
        if "duplicate" in str(insert.error).lower() or "conflict" in str(insert.error).lower():
            return {"status": "exists", "watchlist_id": watchlist_id}
        raise RuntimeError(f"Failed to add stock to watchlist: {insert.error}")

    return {"status": "added", "watchlist_id": watchlist_id}

def get_watchlist_count(ticker: str) -> int:
    ticker = ticker.upper()
    # We request exact count metadata
    res = supabase.table("watchlist_stocks").select("ticker", count="exact").eq("ticker", ticker).execute()
    if res.error:
        raise RuntimeError(f"Supabase error: {res.error}")
    if hasattr(res, "count") and isinstance(res.count, int):
        return int(res.count)
    # fallback
    return len(res.data or [])
