# api/watchlist.py
from __future__ import annotations
from typing import List, Dict, Tuple
from sqlalchemy.engine import Engine
from sqlalchemy import text, bindparam


def get_or_create_default_watchlist(rds: Engine, user_id: str) -> Dict:
    sql_sel = text("""
        SELECT watchlist_id, user_id, name, description, created_at
        FROM public.watchlists
        WHERE user_id = :uid
        ORDER BY created_at DESC
        LIMIT 1
    """)
    sql_ins = text("""
        INSERT INTO public.watchlists (user_id, name, description)
        VALUES (:uid, 'default', 'User default watchlist')
        RETURNING watchlist_id, user_id, name, description, created_at
    """)
    with rds.begin() as conn:
        row = conn.execute(sql_sel, {"uid": user_id}).mappings().first()
        if row:
            return dict(row)
        created = conn.execute(sql_ins, {"uid": user_id}).mappings().first()
        return dict(created)


def list_watchlist_items(rds: Engine, watchlist_id: str) -> Tuple[List[Dict], Dict[str, str]]:
    sql_items = text("""
        SELECT watchlist_id, ticker, allocation, added_at
        FROM public.watchlist_stocks
        WHERE watchlist_id = :wid
        ORDER BY added_at
    """)
    with rds.connect() as conn:
        items = [dict(r) for r in conn.execute(sql_items, {"wid": watchlist_id}).mappings().all()]
        tickers = [r["ticker"] for r in items]

        name_map: Dict[str, str] = {}
        if tickers:
            sql_names = (
                text("""
                    SELECT ticker, COALESCE(short_name, name, ticker) AS disp
                    FROM public.companies
                    WHERE ticker IN :tickers
                """)
                .bindparams(bindparam("tickers", expanding=True))
            )
            for r in conn.execute(sql_names, {"tickers": tickers}).mappings().all():
                name_map[r["ticker"]] = r["disp"]

    print(items,name_map)
    return items, name_map


def upsert_watchlist_item(rds: Engine, watchlist_id: str, ticker: str, allocation: float) -> None:
    sql = text("""
        INSERT INTO public.watchlist_stocks (watchlist_id, ticker, allocation)
        VALUES (:wid, :tkr, :alloc)
        ON CONFLICT (watchlist_id, ticker)
        DO UPDATE SET allocation = EXCLUDED.allocation
    """)
    with rds.begin() as conn:
        conn.execute(sql, {"wid": watchlist_id, "tkr": (ticker or "").upper().strip(), "alloc": float(allocation)})


def delete_watchlist_item(rds: Engine, watchlist_id: str, ticker: str) -> None:
    sql = text("""
        DELETE FROM public.watchlist_stocks
        WHERE watchlist_id = :wid AND ticker = :tkr
    """)
    with rds.begin() as conn:
        conn.execute(sql, {"wid": watchlist_id, "tkr": (ticker or "").upper().strip()})


def update_watchlist_item(rds: Engine, watchlist_id: str, old_ticker: str, new_ticker: str, allocation: float) -> None:
    old_t = (old_ticker or "").upper().strip()
    new_t = (new_ticker or "").upper().strip()
    alloc = float(allocation)

    if new_t == old_t:
        sql = text("""
            UPDATE public.watchlist_stocks
            SET allocation = :alloc
            WHERE watchlist_id = :wid AND ticker = :tkr
        """)
        with rds.begin() as conn:
            conn.execute(sql, {"alloc": alloc, "wid": watchlist_id, "tkr": old_t})
        return

    sql_upsert_new = text("""
        INSERT INTO public.watchlist_stocks (watchlist_id, ticker, allocation)
        VALUES (:wid, :tkr, :alloc)
        ON CONFLICT (watchlist_id, ticker)
        DO UPDATE SET allocation = EXCLUDED.allocation
    """)
    sql_delete_old = text("""
        DELETE FROM public.watchlist_stocks
        WHERE watchlist_id = :wid AND ticker = :tkr
    """)
    with rds.begin() as conn:
        conn.execute(sql_upsert_new, {"wid": watchlist_id, "tkr": new_t, "alloc": alloc})
        conn.execute(sql_delete_old, {"wid": watchlist_id, "tkr": old_t})
