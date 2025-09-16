# views/user/watchlist.py
from __future__ import annotations
import os, requests
from typing import Any, Dict, List, Optional
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SR_KEY = os.getenv("SUPABASE_SERVICE_ROLE")  # preferred for dev/no-signin
ANON = os.getenv("SUPABASE_ANON_KEY", "")

DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "24743632-db93-4f83-bf63-6f995cb6a6d6")

def _hdrs() -> Dict[str, str]:
    key = SR_KEY or ANON
    if not SUPABASE_URL or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE/ANON key in env.")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def _list_watchlists(user_id: Optional[str]) -> List[Dict[str, Any]]:
    params = {
        "select": "watchlist_id,name,description,created_at,user_id,watchlist_stocks(ticker,added_at)",
        "order": "created_at.asc",
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
    r = requests.get(f"{SUPABASE_URL}/rest/v1/watchlists", headers=_hdrs(), params=params, timeout=15)
    r.raise_for_status()
    return r.json() or []

def _ensure_default_watchlist(user_id: str) -> str:
    # lookup
    q = {"user_id": f"eq.{user_id}", "name": "eq.default", "select": "watchlist_id", "limit": "1"}
    g = requests.get(f"{SUPABASE_URL}/rest/v1/watchlists", headers=_hdrs(), params=q, timeout=15)
    g.raise_for_status()
    rows = g.json()
    if rows:
        return rows[0]["watchlist_id"]
    # insert
    ins = requests.post(
        f"{SUPABASE_URL}/rest/v1/watchlists",
        headers=_hdrs(),
        json={"user_id": user_id, "name": "default", "description": "Default watchlist"},
        timeout=15,
    )
    ins.raise_for_status()
    return ins.json()[0]["watchlist_id"]

def _add_ticker(user_id: str, ticker: str, watchlist_name: str = "default") -> Dict[str, Any]:
    wid = _ensure_default_watchlist(user_id)
    headers = _hdrs()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    params = {"on_conflict": "watchlist_id,ticker"}
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/watchlist_stocks",
        headers=headers,
        params=params,
        json={"watchlist_id": wid, "ticker": ticker.upper().strip()},
        timeout=15,
    )
    if r.status_code in (200, 201):
        return {"status": "added"} if r.json() else {"status": "exists"}
    if r.status_code == 409:
        return {"status": "exists"}
    r.raise_for_status()
    return {"status": "added"}

def _remove_ticker(watchlist_id: str, ticker: str) -> None:
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/watchlist_stocks",
        headers=_hdrs(),
        params={"watchlist_id": f"eq.{watchlist_id}", "ticker": f"eq.{ticker.upper().strip()}"},
        timeout=15,
    )
    if r.status_code not in (200, 204):
        r.raise_for_status()

def user_page(session, supabase) -> None:
    st.title("🔖 Watchlist (no sign-in required)")

    # Sidebar: choose scope
    with st.sidebar:
        st.subheader("Scope")
        show_all = st.checkbox("Show ALL users' watchlists", value=True,
                               help="RLS is off; this lists everything.")
        chosen_user = st.text_input("User ID for actions / filtering",
                                    value=DEFAULT_USER_ID,
                                    help="Used for create/add actions and filtering when 'ALL' is off.")
        st.caption(f"Using key: {'SERVICE-ROLE' if SR_KEY else 'ANON'}")

    # Load watchlists
    try:
        wlists = _list_watchlists(None if show_all else (chosen_user or None))
    except Exception as e:
        st.error(f"Failed to load watchlists: {e}")
        return

    if not wlists:
        st.info("No watchlists found.")
        # quick action to create default for chosen user
        if st.button("Create default for chosen user"):
            try:
                wid = _ensure_default_watchlist(chosen_user or DEFAULT_USER_ID)
                st.success(f"Default created: {wid}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
        return

    # Master/detail
    c1, c2 = st.columns([1, 2], gap="large")

    with c1:
        st.subheader("Watchlists")
        labels = {
            f"{w.get('name') or 'Untitled'} — {w.get('user_id','?')[:8]} — {w.get('watchlist_id','')[:8]}": w
            for w in wlists
        }
        sel = st.selectbox("Select a watchlist", list(labels.keys()))
        selected = labels[sel]

        st.caption("Metadata")
        st.json({
            "watchlist_id": selected.get("watchlist_id"),
            "user_id": selected.get("user_id"),
            "name": selected.get("name"),
            "description": selected.get("description"),
            "created_at": selected.get("created_at"),
        })

    with c2:
        st.subheader("Tickers")
        rows = selected.get("watchlist_stocks") or []
        tickers = sorted([r["ticker"] for r in rows if r.get("ticker")])
        if tickers:
            st.dataframe({"ticker": tickers}, use_container_width=True)
        else:
            st.info("No tickers yet.")

        st.divider()
        st.subheader("Actions (operate on the sidebar User ID)")

        a1, _ = st.columns(2)
        with a1:
            if st.button("Ensure Default Watchlist"):
                try:
                    wid = _ensure_default_watchlist(chosen_user or DEFAULT_USER_ID)
                    st.success(f"Default ensured: {wid}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

        with st.form("add_ticker_form", clear_on_submit=True):
            t = st.text_input("Add ticker to DEFAULT watchlist", placeholder="e.g., AAPL")
            submit = st.form_submit_button("Add")
            if submit:
                if not (t or "").strip():
                    st.warning("Please enter a ticker.")
                else:
                    try:
                        out = _add_ticker(chosen_user or DEFAULT_USER_ID, t)
                        st.success(f"{t.upper()} — {out.get('status','ok')}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add: {e}")

        if tickers:
            st.markdown("**Remove from this selected watchlist**")
            cols = st.columns(6)
            for i, t in enumerate(tickers):
                with cols[i % 6]:
                    if st.button(f"Remove {t}", key=f"rm_{selected['watchlist_id']}_{t}"):
                        try:
                            _remove_ticker(selected["watchlist_id"], t)
                            st.success(f"Removed {t}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to remove {t}: {e}")
