from __future__ import annotations
import math
import streamlit as st
from typing import Optional
from sqlalchemy.engine import Engine
from api.admin_content import (
    admin_list_content, admin_count_content,
    admin_create_content, admin_update_content, admin_delete_content,
)

# Define the custom CSS injection function
def _custom_css():
    st.markdown(
        """
        <style>
        /* Background Color */
        body {
            background-color: #f4f4f9;
        }

        /* Title Styling */
        .css-1f4nmg3 {
            font-family: 'Roboto', sans-serif;
            font-weight: 600;
            color: #333;
            font-size: 28px;
        }

        /* Button Styling */
        .stButton > button {
            background-color: #0077b6;
            color: white;
            border-radius: 5px;
            font-size: 16px;
            padding: 0.5rem 1rem;
            transition: background-color 0.3s ease;
        }

        .stButton > button:hover {
            background-color: #00b4d8;
        }

        /* Input Styling */
        .stTextInput input {
            font-size: 14px;
            padding: 0.5rem;
            border-radius: 5px;
        }

        .stSelectbox, .stTextArea {
            font-size: 14px;
            border-radius: 5px;
        }

        .stCheckbox {
            font-size: 14px;
        }

        /* Sidebar Styling */
        .css-1d391kg {
            background-color: #f0f0f0;
        }

        .badge {
            background: #eef2ff;
            border: 1px solid #dbeafe;
            color: #1e40af;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 12px;
            margin-right: 6px;
        }

        .row-hr {
            border: none;
            border-bottom: 1px solid #eee;
            margin: 0.35rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

def _tag_str(tags) -> str:
    return ", ".join(tags or [])

def _pill(text: str) -> str:
    return f"<span class='badge'>{text}</span>"

def page(rds: Optional[Engine] = None, **kwargs):
    _ = kwargs
    if rds is None:
        st.error("RDS engine is required: router must call page(rds=engine).")
        st.stop()

    _custom_css()  # Inject custom CSS
    st.title("🛠️ Admin — Content Manager")
    st.caption("Create, edit, publish, and delete content shown on the user Home page.")

    with st.expander("➕ Create new content", expanded=False):
        c1, c2 = st.columns([1.4, 1.0])
        with c1:
            new_title = st.text_input("Title")
            new_slug = st.text_input("Slug (optional — auto from title if empty)")
            new_excerpt = st.text_input("Excerpt (optional)")
            new_image = st.text_input("Image URL (optional)")
        with c2:
            new_tkr_in = st.text_input("Ticker (optional)")
            new_ticker = (new_tkr_in or "").upper().strip() or None
            new_type = st.selectbox("Type", ["analysis", "news", "education", "portfolio_tip", "market_update", "opinion"], index=0)
            new_tags_csv = st.text_input("Tags (comma-separated)")
            publish_now = st.checkbox("Publish now?", value=True)
        new_body = st.text_area("Body (Markdown)", height=140, placeholder="Write your content here…")

        if st.button("Create", type="primary"):
            if not new_title or not new_body:
                st.warning("Title and Body are required.")
            else:
                try:
                    row = admin_create_content(
                        rds,
                        title=new_title, body=new_body,
                        author_id=None,
                        slug=new_slug or None,
                        excerpt=new_excerpt or None,
                        image_url=new_image or None,
                        ticker=new_ticker,
                        tags=new_tags_csv,
                        content_type=new_type,
                        publish_now=publish_now,
                    )
                    st.success(f"Created: {row.get('title')}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to create content: {e}")

    st.markdown("<hr class='row-hr' />", unsafe_allow_html=True)

    f1, f2, f3, f4, f5 = st.columns([1.2, 1.0, 1.0, 1.2, 0.6])
    with f1:
        search = st.text_input("Search title/slug/excerpt", placeholder="e.g., NVDA, RSI") or None
    with f2:
        t_in = st.text_input("Ticker", placeholder="e.g., AAPL")
        ticker = (t_in or "").upper().strip() or None
    with f3:
        ctype = st.selectbox("Type", ["(any)", "analysis", "news", "education", "portfolio_tip", "market_update", "opinion"], index=0)
        content_type = None if ctype == "(any)" else ctype
    with f4:
        status = st.selectbox("Status", ["all", "published", "drafts"], index=0)
    with f5:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        apply_clicked = st.button("Apply", use_container_width=True)

    st.markdown("<hr class='row-hr' />", unsafe_allow_html=True)

    if "admin_content_page" not in st.session_state:
        st.session_state.admin_content_page = 1
    if "admin_page_size" not in st.session_state:
        st.session_state.admin_page_size = 10
    if apply_clicked:
        st.session_state.admin_content_page = 1

    pcol_prev, pcol_mid, pcol_next, pcol_size = st.columns([0.5, 2.4, 0.5, 0.8])
    with pcol_size:
        page_size = st.selectbox(
            "", [5, 10, 20, 50],
            index=[5,10,20,50].index(st.session_state.admin_page_size),
            label_visibility="collapsed"
        )
        st.session_state.admin_page_size = page_size

    try:
        total_rows = admin_count_content(
            rds, search=search, ticker=ticker,
            content_type=content_type, status=status
        )
    except Exception as e:
        st.error(f"Failed to count content: {e}")
        st.stop()

    total_pages = max(1, math.ceil(total_rows / st.session_state.admin_page_size))

    with pcol_prev:
        if st.button("←", disabled=(st.session_state.admin_content_page <= 1)):
            st.session_state.admin_content_page = max(1, st.session_state.admin_content_page - 1)
    with pcol_mid:
        st.caption(f"{total_rows} item(s) • Page {st.session_state.admin_content_page} of {total_pages}")
    with pcol_next:
        if st.button("→", disabled=(st.session_state.admin_content_page >= total_pages)):
            st.session_state.admin_content_page = min(total_pages, st.session_state.admin_content_page + 1)

    st.markdown("<hr class='row-hr' />", unsafe_allow_html=True)

    try:
        rows = admin_list_content(
            rds,
            page=st.session_state.admin_content_page,
            page_size=st.session_state.admin_page_size,
            search=search, ticker=ticker,
            content_type=content_type, status=status,
        )
    except Exception as e:
        st.error(f"Failed to fetch content: {e}")
        st.stop()

    if not rows:
        st.info("No content found.")
        return

    for r in rows:
        with st.container():
            top = st.columns([3, 1.8, 1.2, 1.1, 0.9, 0.9])
            with top[0]:
                st.markdown(f"**{r.get('title') or 'Untitled'}**")
                chips = []
                if r.get("content_type"): chips.append(_pill(r["content_type"]))
                if r.get("ticker"): chips.append(_pill(r["ticker"]))
                chips.append(_pill("📅 published" if r.get("published_at") else "📝 draft"))
                st.markdown(" ".join(chips), unsafe_allow_html=True)
                st.caption(f"slug: `{r.get('slug')}` • id: `{r.get('id')}`")
            with top[1]:
                st.caption("Excerpt")
                st.write(r.get("excerpt") or "")
            with top[2]:
                st.caption("Tags")
                st.write(_tag_str(r.get("tags")))
            with top[3]:
                st.caption("Created")
                st.write(r.get("created_at") or "")
            with top[4]:
                st.caption("Updated")
                st.write(r.get("updated_at") or "")
            with top[5]:
                st.caption("")

            with st.expander("Edit", expanded=False):
                e1, e2 = st.columns([1.4, 1.0])
                with e1:
                    title = st.text_input("Title", value=r.get("title") or "", key=f"title_{r['id']}")
                    slug = st.text_input("Slug", value=r.get("slug") or "", key=f"slug_{r['id']}")
                    excerpt = st.text_input("Excerpt", value=r.get("excerpt") or "", key=f"ex_{r['id']}")
                    image = st.text_input("Image URL", value=r.get("image_url") or "", key=f"img_{r['id']}")
                with e2:
                    tkr_val = (r.get("ticker") or "")
                    ticker_ed = (st.text_input("Ticker", value=tkr_val, key=f"tkr_{r['id']}") or "").upper().strip()
                    types = ["analysis","news","education","portfolio_tip","market_update","opinion"]
                    try:
                        idx = types.index(r.get("content_type") or "analysis")
                    except ValueError:
                        idx = 0
                    ctype_ed = st.selectbox("Type", options=types, index=idx, key=f"ctype_{r['id']}")
                    tags_csv = st.text_input("Tags (csv)", value=_tag_str(r.get("tags")), key=f"tags_{r['id']}")
                    pub_now = st.checkbox("Publish now", value=False, key=f"pub_{r['id']}")
                    unpub = st.checkbox("Unpublish (make draft)", value=False, key=f"unpub_{r['id']}")
                body = st.text_area("Body (Markdown)", value=r.get("body") or "", height=160, key=f"body_{r['id']}")

                bcol1, bcol2, bcol3 = st.columns([0.8, 0.8, 0.9])
                with bcol1:
                    if st.button("💾 Save", key=f"save_{r['id']}"):
                        try:
                            row = admin_update_content(
                                rds, r["id"],
                                title=title, body=body, slug=slug, excerpt=excerpt,
                                image_url=image, ticker=ticker_ed or None, tags=tags_csv,
                                content_type=ctype_ed,
                                publish_now=(True if pub_now else None),
                                unpublish=(True if unpub else None),
                            )
                            st.success(f"Saved: {row.get('title')}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save failed: {e}")
                with bcol2:
                    if st.button("🗑️ Delete", key=f"del_{r['id']}"):
                        try:
                            admin_delete_content(rds, r["id"])
                            st.success("Deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")
                with bcol3:
                    is_pub = r.get("published_at") is not None
                    new_state_label = "Unpublish" if is_pub else "Publish"
                    if st.button(f"🚀 {new_state_label}", key=f"toggle_{r['id']}"):
                        try:
                            if is_pub:
                                admin_update_content(rds, r["id"], unpublish=True)
                            else:
                                admin_update_content(rds, r["id"], publish_now=True)
                            st.success(f"{new_state_label}ed.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Toggle failed: {e}")

        st.markdown("<hr class='row-hr' />", unsafe_allow_html=True)

def admin_home(rds: Optional[Engine] = None, **kwargs):
    return page(rds=rds, **kwargs)

def admin_page(rds: Optional[Engine] = None, **kwargs):
    return page(rds=rds, **kwargs)

def user_page(rds: Optional[Engine] = None, **kwargs):
    return page(rds=rds, **kwargs)
