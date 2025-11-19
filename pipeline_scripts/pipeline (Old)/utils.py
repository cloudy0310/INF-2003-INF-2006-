# etl/utils.py
import os
import json
import pandas as pd

def to_json_text(obj):
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return None

def ensure_dir_for_file(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def upsert_csv(df_new: pd.DataFrame, csv_path: str, key_subset, sort_cols=None):
    """
    Upsert DataFrame into csv_path by merging with existing CSV (if exists),
    dropping duplicates according to key_subset (keeping the last row).
    key_subset: list of column names
    sort_cols: columns to sort by (descending) before writing (optional)
    """
    ensure_dir_for_file(csv_path)
    if os.path.exists(csv_path):
        try:
            df_existing = pd.read_csv(csv_path, dtype=str)
            # preserve original columns + new ones
            df_combined = pd.concat([df_existing, df_new.astype(str)], ignore_index=True, sort=False)
        except Exception as e:
            print(f"[upsert_csv] warning reading existing csv {csv_path}: {e}")
            df_combined = df_new
    else:
        df_combined = df_new

    # Drop duplicates based on key subset
    try:
        if all(col in df_combined.columns for col in key_subset):
            df_combined = df_combined.drop_duplicates(subset=key_subset, keep="last")
        else:
            df_combined = df_combined.drop_duplicates(keep="last")
    except Exception as e:
        print(f"[upsert_csv] drop_duplicates issue: {e}")

    # optional sort
    if sort_cols:
        present_sort = [c for c in sort_cols if c in df_combined.columns]
        if present_sort:
            try:
                df_combined = df_combined.sort_values(by=present_sort, ascending=False)
            except Exception:
                pass

    df_combined.to_csv(csv_path, index=False)
    print(f"[upsert_csv] Wrote {csv_path} ({len(df_combined)} rows)")
