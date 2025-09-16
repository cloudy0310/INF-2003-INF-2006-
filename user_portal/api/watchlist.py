# api/watchlist.py
from __future__ import annotations
from typing import List, Dict, Tuple
from supabase import Client

def get_or_create_default_watchlist(sb: Client, user_id: str) -> Dict:
    """
    Ensure one watchlist per user at the app level.
    Returns the latest/created watchlist row.
    """
    res = (
        sb.table("watchlists")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]

    payload = {"user_id": user_id, "name": "default", "description": "User default watchlist"}
    created = sb.table("watchlists").insert(payload).select("*").single().execute()
    return created.data

def list_watchlist_items(sb: Client, watchlist_id: str) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Returns (items, name_map).
    items: [{watchlist_id,ticker,allocation,added_at}, ...]
    name_map: {'AAPL': 'Apple Inc', ...} (best-effort from companies)
    """
    rows = (
        sb.table("watchlist_stocks")
        .select("watchlist_id,ticker,allocation,added_at")
        .eq("watchlist_id", watchlist_id)
        .order("added_at")
        .execute()
    ).data or []

    tickers = [r["ticker"] for r in rows]
    name_map: Dict[str, str] = {}
    if tickers:
        comps = (
            sb.table("companies")
            .select("ticker,name,short_name")
            .in_("ticker", tickers)
            .execute()
        ).data or []
        for c in comps:
            name_map[c["ticker"]] = c.get("short_name") or c.get("name") or c["ticker"]
    return rows, name_map

def upsert_watchlist_item(sb: Client, watchlist_id: str, ticker: str, allocation: float) -> None:
    payload = {
        "watchlist_id": watchlist_id,
        "ticker": (ticker or "").upper().strip(),
        "allocation": float(allocation),
    }
    sb.table("watchlist_stocks").upsert(payload, on_conflict="watchlist_id,ticker").execute()

def delete_watchlist_item(sb: Client, watchlist_id: str, ticker: str) -> None:
    sb.table("watchlist_stocks").delete() \
      .eq("watchlist_id", watchlist_id) \
      .eq("ticker", (ticker or "").upper().strip()) \
      .execute()

def update_watchlist_item(sb: Client, watchlist_id: str, old_ticker: str, new_ticker: str, allocation: float) -> None:
    """
    If ticker changed, upsert the new key then delete the old key.
    If ticker unchanged, just update allocation.
    """
    old_t = (old_ticker or "").upper().strip()
    new_t = (new_ticker or "").upper().strip()
    alloc = float(allocation)

    if new_t == old_t:
        sb.table("watchlist_stocks").update({"allocation": alloc}) \
          .eq("watchlist_id", watchlist_id).eq("ticker", old_t).execute()
        return

    sb.table("watchlist_stocks").upsert(
        {"watchlist_id": watchlist_id, "ticker": new_t, "allocation": alloc},
        on_conflict="watchlist_id,ticker"
    ).execute()
    sb.table("watchlist_stocks").delete() \
      .eq("watchlist_id", watchlist_id).eq("ticker", old_t).execute()
