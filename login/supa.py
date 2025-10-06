# login/supa.py
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_ANON_KEY in .env")
    return create_client(url, key)
