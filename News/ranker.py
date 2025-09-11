import math, time, re
from typing import List, Tuple
from .news_sources import Article, GOOD_SOURCES_WEIGHT, SIGNAL_WORDS, title_key

_signal_regexes = [(re.compile(p, re.I), w) for p, w in SIGNAL_WORDS.items()]

def _freshness_score(published_ts: int, now_ts: int) -> float:
    if not published_ts: return 0.0
    hours = max(1/60, (now_ts - published_ts)/3600.0)
    return max(0.0, 1.2 * math.exp(-hours/6.0))

def _source_score(source: str) -> float:
    return GOOD_SOURCES_WEIGHT.get(source or "", 0.3)

def _signal_score(text: str) -> float:
    return sum(w for rgx, w in _signal_regexes if rgx.search(text or ""))

def score(a: Article, now_ts:int) -> float:
    return _freshness_score(a.published_ts or 0, now_ts) + _source_score(a.source or "") + _signal_score(f"{a.title} {a.snippet or ''}")

def dedupe_and_rank(articles: List[Article], top_k=12) -> List[Tuple[Article, float]]:
    now = int(time.time())
    seen, scored = set(), []
    for a in articles:
        k = title_key(a.title or a.link or "")
        if k in seen: continue
        seen.add(k)
        scored.append((a, score(a, now)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
