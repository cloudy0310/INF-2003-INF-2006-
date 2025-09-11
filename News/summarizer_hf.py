# summarizer_hf.py
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import os, re
try:
    import streamlit as st
    _ST_SECRETS = st.secrets
except Exception:
    _ST_SECRETS = {}

from .hf_client import HFTextGen

SYSTEM = (
    "You are a careful financial writer. You ONLY use provided facts/links. "
    "Write two short paragraphs: (1) Recent developments (facts only), "
    "(2) Outlook (cautious, based on reported items like earnings/guidance/analyst actions). "
    "No advice or price targets. If catalysts are unclear, say outlook uncertain. "
    "Include 2–3 bracketed citations like [1], [2] that map to the provided URL list order."
)

def _clip(s: str, max_len: int = 180) -> str:
    s = (s or "").strip().replace("\n", " ")
    return (s[:max_len] + "…") if len(s) > max_len else s

def build_context(articles: List[Dict], max_items: int = 5) -> Dict[str, Any]:
    arts = sorted(articles, key=lambda a: a.get("published_ts") or 0, reverse=True)[:max_items]
    bullets, urls = [], []
    for a in arts:
        dt = datetime.fromtimestamp(a["published_ts"], tz=timezone.utc).strftime("%Y-%m-%d") if a.get("published_ts") else "N/A"
        title = _clip(a.get("title", ""), 160)
        src   = _clip(a.get("source", "") or "", 60)
        bullets.append(f"- [{dt}] {title}" + (f" — {src}" if src else ""))
        if a.get("url"):
            urls.append(a["url"])
    return {"bullets": bullets, "urls": urls}

def _prompt(ticker: str, ctx: Dict[str, Any]) -> str:
    numbered = "\n".join(f"[{i+1}] {u}" for i, u in enumerate(ctx["urls"]))
    return f"""[SYSTEM]
{SYSTEM}

[USER]
Ticker: {ticker}

RECENT FACTS:
{chr(10).join(ctx["bullets"])}

SOURCES (use these indices in citations):
{numbered}

OUTPUT:
Two short paragraphs. Add citations like [1], [2] referring to the above URLs.
"""

def summarize_with_hf(
    ticker: str,
    articles: List[Dict],
    hf_token: Optional[str] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    ctx = build_context(articles, max_items=5)
    if not ctx["bullets"]:
        return {
            "summary": "No recent articles found for the selected period.",
            "outlook": "Insufficient information for an outlook.",
            "citations": [],
            "sources": [],
            "confidence": "low",
            "raw": "",
        }

    # resolve token automatically if not passed
    token = hf_token or _ST_SECRETS.get("HF_TOKEN") or os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    client = HFTextGen(api_token=token, model=model or "mistralai/Mistral-7B-Instruct-v0.2")

    text = client.generate(_prompt(ticker, ctx), max_new_tokens=280, temperature=0.25, top_p=0.9)

    # Normalize newlines and split into paragraphs defensively
    text_norm = re.sub(r"\r\n?", "\n", text).strip()
    parts = [p.strip() for p in text_norm.split("\n\n") if p.strip()]
    if len(parts) == 1:
        # fallback: split by sentence boundaries (rough)
        sents = re.split(r"(?<=[.!?])\s+", parts[0])
        parts = [" ".join(sents[:2]).strip(), " ".join(sents[2:]).strip()] if len(sents) > 2 else [parts[0], ""]

    # Extract citation indices like [2], [3]; clamp to available URLs
    cited = sorted({int(m.group(1)) for m in re.finditer(r"\[(\d{1,2})\]", text_norm)
                    if 1 <= int(m.group(1)) <= len(ctx["urls"])})

    return {
        "summary": parts[0] if parts else "",
        "outlook": parts[1] if len(parts) > 1 else "",
        "citations": cited,
        "sources": ctx["urls"],
        "confidence": "medium" if cited else "low",
        "raw": text_norm,
    }
