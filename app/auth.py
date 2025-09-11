# app/auth.py
import streamlit as st
from typing import Optional, Tuple, Any, Dict
from supabase import create_client, Client

# ---------- Config / client ----------

def get_supabase_client() -> Client:
    """
    Create or reuse a Supabase client from streamlit secrets.
    Expects st.secrets["SUPABASE"]["SUPABASE_URL"] and ["SUPABASE_ANON_KEY"].
    """
    try:
        url = st.secrets["SUPABASE"]["SUPABASE_URL"]
        anon = st.secrets["SUPABASE"]["SUPABASE_ANON_KEY"]
    except Exception as e:
        raise RuntimeError(
            "Supabase secrets missing. Add SUPABASE_URL and SUPABASE_ANON_KEY to .streamlit/secrets.toml"
        ) from e

    if "supabase_client" not in st.session_state:
        st.session_state["supabase_client"] = create_client(url, anon)
    return st.session_state["supabase_client"]

# ---------- Helpers ----------

def _ok(user: Optional[Any], access_token: Optional[str], raw: Any = None) -> Dict:
    return {"user": user, "access_token": access_token, "raw": raw, "error": None}

def _err(msg: str, raw: Any = None) -> Dict:
    return {"user": None, "access_token": None, "raw": raw, "error": msg}

def _normalize_auth_response(res: Any) -> Tuple[Optional[Any], Optional[str], Any]:
    """
    Return (user, access_token, raw)
    Handles:
      - dict responses
      - AuthResponse-like objects (with .user and .session)
      - Response-like objects with .json()
    """
    user = None
    access_token = None
    raw = res

    # 1) dict-like
    if isinstance(res, dict):
        user = res.get("user") or (res.get("data") or {}).get("user")
        access_token = (
            res.get("access_token")
            or (res.get("data") or {}).get("access_token")
            or (res.get("data") or {}).get("session", {}).get("access_token")
        )
        return user, access_token, raw

    # 2) AuthResponse-like object (supabase-py)
    # Typical attributes: .user, .session
    if hasattr(res, "user") or hasattr(res, "session"):
        try:
            user_attr = getattr(res, "user", None)
            session_attr = getattr(res, "session", None)
            if user_attr:
                user = user_attr
            if session_attr:
                # session may be an object with access_token
                access_token = getattr(session_attr, "access_token", None)
                # session.user may contain user too
                if not user and hasattr(session_attr, "user"):
                    user = getattr(session_attr, "user")
            # Some SDKs embed user/session under .data
            if not user and hasattr(res, "data"):
                data = getattr(res, "data", None)
                if isinstance(data, dict):
                    user = data.get("user") or user
                    access_token = access_token or data.get("access_token")
        except Exception:
            pass

        if user or access_token:
            return user, access_token, raw

    # 3) Try .json()
    try:
        j = res.json()
        if isinstance(j, dict):
            user = j.get("user") or (j.get("data") or {}).get("user")
            access_token = (
                j.get("access_token")
                or (j.get("data") or {}).get("access_token")
                or (j.get("data") or {}).get("session", {}).get("access_token")
            )
            return user, access_token, raw
    except Exception:
        pass

    return None, None, raw

def _user_to_dict(user_obj: Any) -> dict:
    """
    Convert a user-like object to a basic dict with commonly used fields.
    Safe fallback when SDK returns a user object instead of a dict.
    """
    if user_obj is None:
        return {}
    if isinstance(user_obj, dict):
        return user_obj
    # Try to access attributes commonly present
    out = {}
    for k in ("id", "sub", "email", "aud", "role", "created_at", "updated_at"):
        try:
            val = getattr(user_obj, k, None)
            if val is None:
                # some user objects nested: user.user.id etc
                try:
                    val = user_obj.__dict__.get(k)
                except Exception:
                    val = None
            if val is not None:
                out[k] = val
        except Exception:
            continue
    # as a fallback, try __dict__
    try:
        if not out and hasattr(user_obj, "__dict__"):
            out = dict(user_obj.__dict__)
    except Exception:
        pass
    return out

# ---------- Auth operations ----------

def signup(email: str, password: str, username: Optional[str] = None) -> Dict:
    """
    Robust signup:
      - tries sign_up variants without unsupported kwargs
      - normalizes response
      - optionally attempts to upsert public.users row with username (client-side; may be blocked by RLS)
    """
    try:
        supabase = get_supabase_client()
    except Exception as e:
        return _err(f"Supabase init error: {e}")

    res = None
    try:
        # Try: prefer passing only credentials (most compatible)
        try:
            res = supabase.auth.sign_up({"email": email, "password": password})
        except TypeError:
            # legacy fallback patterns (attempt other signatures if available)
            try:
                res = supabase.auth.sign_up({"email": email, "password": password}, {"data": {"username": username} if username else {}})
            except Exception:
                try:
                    res = supabase.auth.sign_up({"email": email, "password": password}, user_metadata={"username": username} if username else {})
                except Exception:
                    # give up and return error
                    return _err("Signup call failed: unsupported sign_up signature", raw=None)
    except Exception as e:
        return _err(f"Signup call failed: {e}")

    # Normalize
    user, access_token, raw = _normalize_auth_response(res)

    # If user is an SDK object, convert minimally for storage/display
    user_dict = _user_to_dict(user) if user is not None else None

    # If we have user and provided username, try to upsert public.users (may fail due to RLS)
    if user_dict and username:
        try:
            user_id = user_dict.get("id") or user_dict.get("sub")
            if user_id:
                upsert_resp = supabase.table("users").upsert(
                    {"user_id": user_id, "email": user_dict.get("email"), "username": username}
                ).execute()
                raw = {"signup_raw": raw, "upsert_profile_raw": upsert_resp}
        except Exception:
            # ignore; client-side cannot always write profile due to RLS
            pass

    if not user:
        return _err("Signup failed: no user returned", raw=raw)

    # store into session_state for convenience
    try:
        st.session_state["user"] = user_dict
        if access_token:
            st.session_state["access_token"] = access_token
    except Exception:
        pass

    return _ok(user_dict, access_token, raw=raw)

def login(email: str, password: str) -> Dict:
    """
    Login with password. Handles different SDK method names.
    """
    try:
        supabase = get_supabase_client()
    except Exception as e:
        return _err(f"Supabase init error: {e}")

    res = None
    try:
        # modern API
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        except AttributeError:
            # older: sign_in
            try:
                res = supabase.auth.sign_in({"email": email, "password": password})
            except Exception as e:
                return _err(f"Login call failed: {e}")
    except Exception as e:
        return _err(f"Login call failed: {e}")

    user, access_token, raw = _normalize_auth_response(res)
    user_dict = _user_to_dict(user) if user is not None else None

    if not user:
        return _err("Login failed: no user returned", raw=raw)

    # store into session_state
    try:
        st.session_state["user"] = user_dict
        if access_token:
            st.session_state["access_token"] = access_token
    except Exception:
        pass

    return _ok(user_dict, access_token, raw=raw)

def get_profile(user_id: str, access_token: Optional[str] = None) -> Optional[dict]:
    """
    Fetch profile row from public.users where user_id = provided id.
    If access_token provided, try to attach it to the client to respect RLS.
    """
    try:
        supabase = get_supabase_client()
    except Exception as e:
        raise RuntimeError(f"Supabase init error: {e}")

    client = supabase
    # try to clone with auth header if token present (create_client may accept headers map)
    if access_token:
        try:
            url = st.secrets["SUPABASE"]["SUPABASE_URL"]
            anon = st.secrets["SUPABASE"]["SUPABASE_ANON_KEY"]
            # second arg is anon key; third can be options dict with headers in some versions
            client = create_client(url, anon, {"Authorization": f"Bearer {access_token}"})
        except Exception:
            # ignore and fall back to anon client
            client = supabase

    try:
        resp = client.table("users").select("*").eq("user_id", user_id).limit(1).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch profile: {e}")

    data = None
    if isinstance(resp, dict):
        data = resp.get("data")
    else:
        try:
            # resp.data is typical in newer supabase clients
            data = getattr(resp, "data", None)
        except Exception:
            try:
                data = resp.json().get("data")
            except Exception:
                data = None

    if not data:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data
