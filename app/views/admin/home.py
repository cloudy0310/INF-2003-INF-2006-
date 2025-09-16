import streamlit as st
from datetime import datetime, timezone
import json
import re

def safe_rerun():
    try:
        if hasattr(st, "rerun"):
            return st.rerun()
    except:
        try:
            st.stop()
        except:
            pass

def _unwrap(res):
    # handle different supabase client shapes
    if res is None:
        return None, "no response"
    if hasattr(res, "data") and hasattr(res, "error"):
        return res.data, res.error
    if isinstance(res, dict):
        return res.get("data"), res.get("error")
    return getattr(res, "data", None), getattr(res, "error", None)

def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text[:200]

def _get_user_id(session):
    try:
        return session.user.id
    except Exception:
        try:
            return getattr(session.user, "user_id")
        except Exception:
            if isinstance(session, dict):
                return (session.get("user") or {}).get("id") or (session.get("user") or {}).get("user_id")
    return None

def admin_home(session, supabase):
    """Admin CMS UI: list, create, edit, delete, publish."""
    st.title("🔧 Admin CMS")

    user_email = None
    try:
        user_email = session.user.email
    except Exception:
        if isinstance(session, dict):
            user_email = (session.get("user") or {}).get("email")

    st.caption(f"Signed in as: {user_email}")

    col1, col2 = st.columns([2, 1])

    # Left: list content
    with col1:
        st.header("Content list")
        query = st.text_input("Search by title or tag", key="cms_search")
        show_published = st.selectbox("Show", ["All", "Published", "Drafts"], key="cms_show")

        # fetch content
        try:
            supq = supabase.table("content").select("*")
            res = supq.execute()
            items, err = _unwrap(res)
            if err:
                st.error(f"Failed to fetch content: {err}")
                items = []
        except Exception as e:
            st.error(f"Failed to fetch content: {e}")
            items = []

        if items is None:
            items = []

        def matches(item):
            if not item:
                return False
            title = (item.get("title") or "")
            tags = item.get("tags") or []
            published_at = item.get("published_at")
            if show_published == "Published" and not published_at:
                return False
            if show_published == "Drafts" and published_at:
                return False
            if query:
                q = query.lower()
                if q in title.lower():
                    return True
                if any(q in (t or "").lower() for t in tags):
                    return True
                return False
            return True

        filtered = [it for it in items if matches(it)]
        filtered.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "", reverse=True)

        for i, row in enumerate(filtered):
            with st.expander(f"{row.get('title')}  —  {row.get('id')}"):
                st.write(f"**Author:** {row.get('author_id')}")
                st.write(f"**Slug:** {row.get('slug')}")
                st.write(f"**Published at:** {row.get('published_at')}")
                st.write(f"**Tags:** {', '.join(row.get('tags') or [])}")
                if row.get("image_url"):
                    st.image(row.get("image_url"), width=250)
                st.markdown(row.get("excerpt") or "_No excerpt_")

                col_a, col_b, col_c = st.columns([1,1,2])
                if col_a.button("Edit", key=f"edit_{row.get('id')}"):
                    st.session_state.cms_selected_id = row.get('id')
                    safe_rerun()
                if col_b.button("Delete", key=f"delete_{row.get('id')}"):
                    st.session_state.cms_delete_pending = row.get('id')
                    safe_rerun()
                with col_c:
                    if st.button("Preview", key=f"preview_{row.get('id')}"):
                        st.markdown(row.get('body') or "")

    # Right: create / edit / delete panel
    with col2:
        st.header("Editor")
        selected = st.session_state.get("cms_selected_id")
        delete_pending = st.session_state.get("cms_delete_pending")

        if delete_pending:
            st.warning("Delete pending — this will remove the content permanently")
            if st.button("Confirm delete"):
                try:
                    res = supabase.table("content").delete().eq("id", delete_pending).execute()
                    data, err = _unwrap(res)
                    if err:
                        st.error(f"Delete failed: {err}")
                    else:
                        st.success("Deleted")
                        st.session_state.cms_delete_pending = None
                        st.session_state.cms_selected_id = None
                        safe_rerun()
                except Exception as e:
                    st.error(f"Delete error: {e}")
            if st.button("Cancel delete"):
                st.session_state.cms_delete_pending = None
                safe_rerun()

        if selected:
            st.info(f"Editing: {selected}")
            try:
                res = supabase.table("content").select("*").eq("id", selected).single().execute()
                data, err = _unwrap(res)
                if err:
                    st.error(f"Failed to load: {err}")
                    data = {}
            except Exception as e:
                st.error(f"Load error: {e}")
                data = {}
            # populate form
            title = st.text_input("Title", value=data.get("title") or "", key="cms_title")
            slug = st.text_input("Slug (optional)", value=data.get("slug") or "", key="cms_slug")
            excerpt = st.text_area("Excerpt", value=data.get("excerpt") or "", key="cms_excerpt")
            image_url = st.text_input("Image URL", value=data.get("image_url") or "", key="cms_image")
            ticker = st.text_input("Ticker (optional)", value=data.get("ticker") or "", key="cms_ticker")
            tags = st.text_input("Tags (comma-separated)", value=(",".join(data.get("tags") or []) or ""), key="cms_tags")
            body = st.text_area("Body (markdown)", value=data.get("body") or "", height=300, key="cms_body")

            # replaced datetime_input with date_input + time_input
            pub = st.checkbox("Published", value=bool(data.get("published_at")), key="cms_pub")
            if pub:
                try:
                    existing = datetime.fromisoformat(data.get("published_at")) if data.get("published_at") else datetime.utcnow()
                except Exception:
                    existing = datetime.utcnow()
                date_val = st.date_input("Publish date", value=existing.date(), key="cms_published_date")
                time_val = st.time_input("Publish time", value=existing.time().replace(microsecond=0), key="cms_published_time")
                published_at = datetime.combine(date_val, time_val)
            else:
                published_at = None

            if st.button("Save changes"):
                payload = {
                    "title": title,
                    "slug": slug or _slugify(title),
                    "excerpt": excerpt,
                    "image_url": image_url,
                    "ticker": ticker or None,
                    "tags": [t.strip() for t in tags.split(",") if t.strip()],
                    "body": body,
                    "updated_at": datetime.utcnow().isoformat(),
                    "raw_meta": json.dumps({"editor": "streamlit-admin"})
                }
                if pub and published_at:
                    payload["published_at"] = published_at.isoformat()
                else:
                    payload["published_at"] = None

                try:
                    res = supabase.table("content").update(payload).eq("id", selected).execute()
                    data, err = _unwrap(res)
                    if err:
                        st.error(f"Update failed: {err}")
                    else:
                        st.success("Updated")
                        st.session_state.cms_selected_id = None
                        safe_rerun()
                except Exception as e:
                    st.error(f"Save error: {e}")

            if st.button("Cancel edit"):
                st.session_state.cms_selected_id = None
                safe_rerun()

        else:
            st.info("Create new content")
            title = st.text_input("Title", key="cms_new_title")
            slug = st.text_input("Slug (optional)", key="cms_new_slug")
            excerpt = st.text_area("Excerpt", key="cms_new_excerpt")
            image_url = st.text_input("Image URL", key="cms_new_image")
            ticker = st.text_input("Ticker (optional)", key="cms_new_ticker")
            tags = st.text_input("Tags (comma-separated)", key="cms_new_tags")
            body = st.text_area("Body (markdown)", height=300, key="cms_new_body")

            # replaced datetime_input with date_input + time_input
            pub = st.checkbox("Publish now", key="cms_new_pub")
            if pub:
                # default to now
                now = datetime.utcnow()
                published_date = st.date_input("Publish date", value=now.date(), key="cms_new_published_date")
                published_time = st.time_input("Publish time", value=now.time().replace(microsecond=0), key="cms_new_published_time")
                published_at = datetime.combine(published_date, published_time)
            else:
                published_at = None

            if st.button("Create content"):
                author_id = _get_user_id(session)
                payload = {
                    "title": title,
                    "slug": slug or _slugify(title),
                    "excerpt": excerpt,
                    "image_url": image_url,
                    "ticker": ticker or None,
                    "tags": [t.strip() for t in tags.split(",") if t.strip()],
                    "body": body,
                    "author_id": author_id,
                    "raw_meta": json.dumps({"created_by": author_id}),
                }
                if pub and published_at:
                    payload["published_at"] = published_at.isoformat()
                try:
                    res = supabase.table("content").insert(payload).execute()
                    data, err = _unwrap(res)
                    if err:
                        st.error(f"Create failed: {err}")
                    else:
                        st.success("Created")
                        for k in ["cms_new_title", "cms_new_slug", "cms_new_excerpt", "cms_new_image", "cms_new_ticker", "cms_new_tags", "cms_new_body", "cms_new_pub", "cms_new_published_date", "cms_new_published_time"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        safe_rerun()
                except Exception as e:
                    st.error(f"Create error: {e}")

    st.divider()
    if st.button("Back to dashboard"):
        st.session_state.current_page = "/admin/home"
        safe_rerun()
