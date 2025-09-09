# etl/supabase_helpers.py
import os
import time
import json
import io
import pandas as pd

try:
    from supabase import create_client
except Exception:
    create_client = None

import psycopg2

def _to_native_value(v):
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v

def prepare_records_for_supabase(df: pd.DataFrame, json_columns=None):
    df2 = df.copy()
    df2 = df2.where(pd.notnull(df2), None)
    records = []
    json_columns = set(json_columns or [])
    for r in df2.to_dict(orient="records"):
        rec = {}
        for k, v in r.items():
            if v is None:
                rec[k] = None
                continue
            if k in json_columns:
                if isinstance(v, (dict, list)):
                    rec[k] = v
                else:
                    try:
                        rec[k] = json.loads(v)
                    except Exception:
                        rec[k] = v
                continue
            rec[k] = _to_native_value(v)
        records.append(rec)
    return records

def upsert_via_supabase(df: pd.DataFrame, table_name: str, supabase_url: str, supabase_key: str,
                       json_columns=None, batch_size: int = 500, sleep: float = 0.05):
    """
    Upsert DataFrame into Supabase table using supabase-py.
    Requires supabase-py installed and a server key (service_role) for writes if RLS blocks anon.
    """
    if create_client is None:
        raise RuntimeError("supabase package not installed. pip install supabase")

    client = create_client(supabase_url, supabase_key)
    records = prepare_records_for_supabase(df, json_columns=json_columns)

    total = len(records)
    if total == 0:
        print(f"[upsert_via_supabase] no records to upsert for {table_name}")
        return

    for i in range(0, total, batch_size):
        batch = records[i:i+batch_size]
        resp = client.table(table_name).upsert(batch).execute()
        # supabase-py returns dict-like or object depending on version
        err = None
        if isinstance(resp, dict):
            err = resp.get("error")
        else:
            err = getattr(resp, "error", None)
        if err:
            print(f"[upsert_via_supabase] ERROR batch {i//batch_size}: {err}")
        else:
            print(f"[upsert_via_supabase] batch {i//batch_size} upserted ({len(batch)} rows) into {table_name}")
        time.sleep(sleep)

def upsert_via_postgres(df: pd.DataFrame, table_name: str, conflict_cols: list, pg_conn=None):
    """
    Upsert using psycopg2:
      1) CREATE TEMP TABLE like target
      2) COPY CSV into temp table
      3) INSERT INTO target SELECT ... FROM temp ON CONFLICT (...) DO UPDATE SET ...
    pg_conn: either a psycopg2 connection string (PG_CONN) or dict with keys host, port, dbname, user, password.
    """
    if df is None or df.empty:
        print("[upsert_via_postgres] no rows to upsert.")
        return

    df2 = df.copy()
    df2 = df2.where(pd.notnull(df2), None)
    cols = list(df2.columns)
    cols_sql = ", ".join(cols)

    # build insert SQL
    set_clause = ", ".join([f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict_cols])
    conflict_sql = ", ".join(conflict_cols)
    insert_sql = f"""
    INSERT INTO {table_name} ({cols_sql})
    SELECT {cols_sql} FROM {table_name}_tmp
    ON CONFLICT ({conflict_sql})
    DO UPDATE SET {set_clause};
    """

    # Use either a URI string from PG_CONN env or a dict
    conn = None
    try:
        if isinstance(pg_conn, str) and pg_conn:
            conn = psycopg2.connect(pg_conn)
        else:
            # read from env if pg_conn not passed
            if pg_conn is None:
                pg_conn = {
                    "host": os.environ.get("PGHOST"),
                    "port": os.environ.get("PGPORT"),
                    "dbname": os.environ.get("PGDATABASE"),
                    "user": os.environ.get("PGUSER"),
                    "password": os.environ.get("PGPASSWORD"),
                }
            # psycopg2.connect accepts these kwargs; ignore None
            conn_kwargs = {k: v for k, v in pg_conn.items() if v is not None}
            conn = psycopg2.connect(**conn_kwargs)

        with conn:
            with conn.cursor() as cur:
                tmp_table = f"{table_name}_tmp"
                # create temp table like actual table
                cur.execute(f"CREATE TEMP TABLE {tmp_table} (LIKE {table_name} INCLUDING ALL);")
                # copy CSV into temp table
                buffer = io.StringIO()
                df2.to_csv(buffer, index=False, header=False)
                buffer.seek(0)
                cur.copy_expert(f"COPY {tmp_table} ({cols_sql}) FROM STDIN WITH CSV", buffer)

                # perform upsert from tmp -> real table
                # Use formatted insert_sql but replace {table_name}_tmp placeholder
                insert_sql_final = insert_sql.replace(f"{table_name}_tmp", tmp_table)
                cur.execute(insert_sql_final)
                print(f"[upsert_via_postgres] upserted {len(df2)} rows into {table_name}")
    finally:
        if conn is not None:
            conn.close()
