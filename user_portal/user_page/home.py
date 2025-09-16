# streamlit_app.py
import streamlit as st
from datetime import datetime, timezone
from app.api.content import supabase_client, list_content

def user_page(limit: int = 10):
    """Simple reader UI that shows published content in a card-like format."""
    st.title("📰 Latest Articles")

    q = st.text_input("Search articles", key="user_search")
    tag_filter = st.text_input("Filter by tag (optional)", key="user_tag")

    # create a server-side supabase client using service role
    try:
        supabase = supabase_client()
    except Exception as e:
        st.error(f"Server misconfiguration: {e}")
        return

    # fetch using wrapper
    res = list_content(supabase, published_only=True, limit=200)
    if res.get("error"):
        st.error(f"Failed to fetch content: {res['error']}")
        data = res.get("data") or []
    else:
        data = res.get("data") or []

    # filter published only and not-in-future
    now_iso = datetime.now(timezone.utc).isoformat()
    articles = [a for a in data if a.get("published_at")]
    articles = [a for a in articles if a.get("published_at") <= now_iso]

    if tag_filter:
        tf = tag_filter.lower()
        articles = [a for a in articles if any(tf in (t or "").lower() for t in (a.get("tags") or []))]

    if q:
        ql = q.lower()
        articles = [a for a in articles if ql in (a.get("title") or "").lower() or ql in (a.get("body") or "").lower()]

    if not articles:
        st.info("No published articles found.")
        return

    for art in articles[:limit]:
        cols = st.columns([1, 3])
        if art.get("image_url"):
            with cols[0]:
                st.image(art.get("image_url"), use_column_width=True)
        with cols[1]:
            st.markdown(f"### {art.get('title')}")
            st.markdown(f"_{art.get('excerpt') or ''}_")
            meta = []
            if art.get("tags"):
                meta.append("Tags: " + ", ".join(art.get("tags")))
            if art.get("ticker"):
                meta.append("Ticker: " + art.get("ticker"))
            if meta:
                st.caption(" · ".join(meta))
            if st.button("Read more", key=f"read_{art.get('id')}"):
                st.markdown(art.get("body") or "")
                st.write("---")


# If you want the page to run when streamlit runs the file:
if __name__ == "__main__":
    user_page(10)
