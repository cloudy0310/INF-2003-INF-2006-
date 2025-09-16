# views/user/watchlist.py
from __future__ import annotations

import os
import requests
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

# Load .env so SUPABASE_URL / keys are available when you run `streamlit run app.py`
load_dotenv()

# --- Config from environment ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")  # preferred for dev "no restrictions"
ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "24743632-db93-4f83-bf63-6f995cb6a6d6")

# --- Helpers ---
def _active_key() -> str:
    """
    Use service-role if provided (dev/admin use only), otherwise anon key.
    """
    key = SERVICE_ROLE or ANON_KEY
    if not SUPABASE_URL or not key:
        raise RuntimeError("Missing SUPABASE_URL or Supabase key(s) in environment.")
    return key

def _hdrs() -> Dict[str, str]:
    key = _active_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _dbg_caption():
    key = SERVICE_ROLE or ANON_KEY or ""
    shown = (key[:8] + "…") if key else "<none>"
    st.caption(
        f"URL: {SUPABASE_URL or '<unset>'} | Key: "
        f"{'SERVICE-ROLE' if SERVICE_ROLE else ('ANON' if ANON_KEY else 'MISSING')} ({shown})"
    )

def _show_http_error(resp: requests.Response, prefix: str):
    try:
        body = resp.text
    except Exception:
        body = "<no body>"
    st.error(f"{prefix}: {resp.status_code} {resp.reason}\n\n{body}")

# --- Data access (PostgREST) ---
def _list_watchlists(user_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Returns watchlists. If user_id is None, returns ALL (RLS must be off or public select granted).
    Embeds watchlist_stocks.
    """
    params = {
        "select": "watchlist_id,name,description,created_at,user_id,watchlist_stocks(ticker,added_at)",
        "order": "created_at.asc",
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"

    url = f"{SUPABASE_URL}/rest/v1/watchlists"
    resp = requests.get(url, headers=_hdrs(), params=params, timeout=20)
    if not resp.ok:
        _show_http_error(resp, "Failed to load watchlists")
        resp.raise_for_status()
    return resp.json() or []

def _ensure_default_watchlist(user_id: str) -> str:
    """
    Get or create the user's 'default' watchlist and return its ID.
    """
    sel_params = {"select": "watchlist_id", "user_id": f"eq.{user_id}", "name": "eq.default", "limit": "1"}
    sel = requests.get(f"{SUPABASE_URL}/rest/v1/watchlists", headers=_hdrs(), params=sel_params, timeout=20)
    if not sel.ok:
        _show_http_error(sel, "Lookup default watchlist failed")
        sel.raise_for_status()
    rows = sel.json() or []
    if rows:
        return rows[0]["watchlist_id"]

    # Insert default
    ins_body = {"user_id": user_id, "name": "default", "description": "Default watchlist"}
    ins = requests.post(f"{SUPABASE_URL}/rest/v1/watchlists", headers=_hdrs(), json=ins_body, timeout=20)
    if not ins.ok:
        _show_http_error(ins, "Create default watchlist failed")
        ins.raise_for_status()
    data = ins.json() or []
    return data[0]["watchlist_id"]

def _add_ticker(user_id: str, ticker: str) -> Dict[str, Any]:
    """
    Add a ticker to the user's default watchlist. Upsert on (watchlist_id, ticker).
    """
    t = (ticker or "").strip().upper()
    if not t:
        raise ValueError("Ticker is required.")
    wid = _ensure_default_watchlist(user_id)

    headers = _hdrs().copy()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    params = {"on_conflict": "watchlist_id,ticker"}

    ins = requests.post(
        f"{SUPABASE_URL}/rest/v1/watchlist_stocks",
        headers=headers,
        params=params,
        json={"watchlist_id": wid, "ticker": t},
        timeout=20,
    )
    if ins.status_code in (200, 201):
        return {"status": "added"} if ins.json() else {"status": "exists"}
    if ins.status_code == 409:
        return {"status": "exists"}
    if not ins.ok:
        _show_http_error(ins, "Add ticker failed")
        ins.raise_for_status()
    return {"status": "added"}

def _remove_ticker(watchlist_id: str, ticker: str) -> None:
    t = (ticker or "").strip().upper()
    if not (watchlist_id and t):
        raise ValueError("watchlist_id and ticker required.")

    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/watchlist_stocks",
        headers=_hdrs(),
        params={"watchlist_id": f"eq.{watchlist_id}", "ticker": f"eq.{t}"},
        timeout=20,
    )
    if resp.status_code not in (200, 204):
        _show_http_error(resp, "Remove ticker failed")
        resp.raise_for_status()

# --- Streamlit page entrypoint (called by your main app) ---
def user_page(session, supabase) -> None:  # signature expected by your router
    st.title("🔖 Watchlist (no sign-in required)")
    _dbg_caption()

    # Sidebar controls
    with st.sidebar:
        st.subheader("Scope")
        all_mode = st.checkbox(
            "Show ALL users' watchlists", value=True,
            help="Requires RLS disabled or public SELECT grants."
        )
        chosen_user = st.text_input(
            "User ID for actions / filtering",
            value=DEFAULT_USER_ID,
            help="Used for create/add actions and filtering when 'ALL' is off."
        )

    # Load data
    try:
        watchlists = _list_watchlists(None if all_mode else (chosen_user or None))
    except requests.HTTPError:
        # Body already shown via _show_http_error
        return
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return

    if not watchlists:
        st.info("No watchlists found.")
        if st.button("Create default for chosen user"):
            try:
                wid = _ensure_default_watchlist(chosen_user or DEFAULT_USER_ID)
                st.success(f"Default created: {wid}")
                st.rerun()
            except requests.HTTPError:
                pass
            except Exception as e:
                st.error(f"Failed: {e}")
        return

    # Master/detail
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.subheader("Watchlists")
        options = {
            f"{w.get('name') or 'Untitled'} — {w.get('user_id','?')[:8]} — {w.get('watchlist_id','')[:8]}": w
            for w in watchlists
        }
        label = st.selectbox("Select a watchlist", list(options.keys()))
        selected = options[label]

        st.caption("Metadata")
        st.json({
            "watchlist_id": selected.get("watchlist_id"),
            "user_id": selected.get("user_id"),
            "name": selected.get("name"),
            "description": selected.get("description"),
            "created_at": selected.get("created_at"),
        })

    with right:
        st.subheader("Tickers in Watchlist")
        rows = selected.get("watchlist_stocks") or []
        tickers = sorted([r["ticker"] for r in rows if r.get("ticker")])

        if tickers:
            st.dataframe({"ticker": tickers}, use_container_width=True)
        else:
            st.info("No tickers yet.")

        st.divider()
        st.subheader("Actions (operate on the sidebar User ID)")

        c1, _ = st.columns(2)
        with c1:
            if st.button("Ensure Default Watchlist"):
                try:
                    wid = _ensure_default_watchlist(chosen_user or DEFAULT_USER_ID)
                    st.success(f"Default ensured: {wid}")
                    st.rerun()
                except requests.HTTPError:
                    pass
                except Exception as e:
                    st.error(f"Failed: {e}")

        with st.form("add_ticker_form", clear_on_submit=True):
            t = st.text_input("Add ticker to DEFAULT watchlist", placeholder="e.g., AAPL")
            submit = st.form_submit_button("Add")
            if submit:
                ticker = (t or "").strip().upper()
                if not ticker:
                    st.warning("Please enter a ticker.")
                else:
                    try:
                        out = _add_ticker(chosen_user or DEFAULT_USER_ID, ticker)
                        st.success(f"{ticker} — {out.get('status','ok')}")
                        st.rerun()
                    except requests.HTTPError:
                        pass
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
                        except requests.HTTPError:
                            pass
                        except Exception as e:
                            st.error(f"Failed to remove {t}: {e}")
