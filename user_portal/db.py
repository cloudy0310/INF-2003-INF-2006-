# db.py
import os
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")  # e.g. mydb.abc123.ap-southeast-1.rds.amazonaws.com
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME")

if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
    raise RuntimeError("Missing DB_USER/DB_PASSWORD/DB_HOST/DB_NAME in environment (.env).")

# Guard: catch accidental Supabase host
if "supabase.co" in DB_HOST:
    raise RuntimeError(f"DB_HOST points to Supabase ({DB_HOST}). Set it to your RDS endpoint.")

url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

engine = create_engine(
    url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# Optional: ensure 'public' is in search_path to match pgAdmin behavior
@event.listens_for(engine, "connect")
def set_search_path(dbapi_conn, _):
    with dbapi_conn.cursor() as cur:
        cur.execute("SET search_path TO public")
