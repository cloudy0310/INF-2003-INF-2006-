-- =========================================================
-- Supabase SQL Setup Script (trimmed & fixed)
-- Replaces any "FOR UPDATE, DELETE" or "FOR INSERT, UPDATE, DELETE"
-- with separate policies per command (Postgres requires this).
-- =========================================================

-- 0. Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- =================================================================
-- Admins table (simple admin list used by RLS policies)
-- =================================================================
CREATE TABLE IF NOT EXISTS admins (
  user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- =================================================================
-- Profiles (user metadata). We reference auth.users for Supabase auth.
-- =================================================================
CREATE TABLE IF NOT EXISTS profiles (
  id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  username text UNIQUE,
  full_name text,
  created_at timestamptz DEFAULT now(),
  metadata jsonb
);

-- Helper admin check function
CREATE OR REPLACE FUNCTION is_admin(uid uuid)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (SELECT 1 FROM admins WHERE user_id = uid);
$$;

-- RLS for profiles: allow owner (or admin) to read/update/insert/delete
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY profiles_select_owner ON profiles
  FOR SELECT
  USING (id = auth.uid() OR is_admin(auth.uid()::uuid));

CREATE POLICY profiles_insert_owner ON profiles
  FOR INSERT
  WITH CHECK (id = auth.uid() OR is_admin(auth.uid()::uuid));

CREATE POLICY profiles_update_owner ON profiles
  FOR UPDATE
  USING (id = auth.uid() OR is_admin(auth.uid()::uuid))
  WITH CHECK (id = auth.uid() OR is_admin(auth.uid()::uuid));

CREATE POLICY profiles_delete_owner ON profiles
  FOR DELETE
  USING (id = auth.uid() OR is_admin(auth.uid()::uuid));

-- =================================================================
-- Stocks (company metadata)
-- =================================================================
CREATE TABLE IF NOT EXISTS stocks (
  ticker text PRIMARY KEY,
  name text,
  exchange text,
  sector text,
  industry text,
  description text,
  metadata jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks (LOWER(name));

-- =================================================================
-- Watchlists + join table (many-to-many)
-- =================================================================
CREATE TABLE IF NOT EXISTS watchlists (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
  name text NOT NULL,
  is_default boolean DEFAULT false,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists (user_id);

CREATE TABLE IF NOT EXISTS watchlist_stocks (
  watchlist_id uuid NOT NULL REFERENCES watchlists (id) ON DELETE CASCADE,
  ticker text NOT NULL REFERENCES stocks (ticker) ON DELETE CASCADE,
  added_at timestamptz DEFAULT now(),
  position int DEFAULT NULL, -- ordering if needed
  note text,
  PRIMARY KEY (watchlist_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_watchliststocks_ticker ON watchlist_stocks (ticker);

-- Watchlists RLS (separate policies for SELECT/INSERT/UPDATE/DELETE)
ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;
CREATE POLICY watchlists_select_owner ON watchlists
  FOR SELECT
  USING (user_id = auth.uid() OR is_admin(auth.uid()::uuid));

CREATE POLICY watchlists_insert_owner ON watchlists
  FOR INSERT
  WITH CHECK (user_id = auth.uid() OR is_admin(auth.uid()::uuid));

CREATE POLICY watchlists_update_owner ON watchlists
  FOR UPDATE
  USING (user_id = auth.uid() OR is_admin(auth.uid()::uuid))
  WITH CHECK (user_id = auth.uid() OR is_admin(auth.uid()::uuid));

CREATE POLICY watchlists_delete_owner ON watchlists
  FOR DELETE
  USING (user_id = auth.uid() OR is_admin(auth.uid()::uuid));

-- Watchlist_stocks RLS (separate policies)
ALTER TABLE watchlist_stocks ENABLE ROW LEVEL SECURITY;
CREATE POLICY watchliststocks_select ON watchlist_stocks
  FOR SELECT
  USING (
    EXISTS (SELECT 1 FROM watchlists w WHERE w.id = watchlist_stocks.watchlist_id AND (w.user_id = auth.uid() OR is_admin(auth.uid()::uuid)))
  );

CREATE POLICY watchliststocks_insert ON watchlist_stocks
  FOR INSERT
  WITH CHECK (
    EXISTS (SELECT 1 FROM watchlists w WHERE w.id = watchlist_stocks.watchlist_id AND (w.user_id = auth.uid() OR is_admin(auth.uid()::uuid)))
  );

CREATE POLICY watchliststocks_update ON watchlist_stocks
  FOR UPDATE
  USING (
    EXISTS (SELECT 1 FROM watchlists w WHERE w.id = watchlist_stocks.watchlist_id AND (w.user_id = auth.uid() OR is_admin(auth.uid()::uuid)))
  )
  WITH CHECK (
    EXISTS (SELECT 1 FROM watchlists w WHERE w.id = watchlist_stocks.watchlist_id AND (w.user_id = auth.uid() OR is_admin(auth.uid()::uuid)))
  );

CREATE POLICY watchliststocks_delete ON watchlist_stocks
  FOR DELETE
  USING (
    EXISTS (SELECT 1 FROM watchlists w WHERE w.id = watchlist_stocks.watchlist_id AND (w.user_id = auth.uid() OR is_admin(auth.uid()::uuid)))
  );

-- =================================================================
-- Financial statements (store metrics as JSONB)
-- =================================================================
CREATE TABLE IF NOT EXISTS financial_statements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker text NOT NULL REFERENCES stocks (ticker),
  period_start date NOT NULL,
  period_end date NOT NULL,
  period_type text NOT NULL, -- e.g. 'annual'|'quarterly'
  reported_at timestamptz,
  currency text,
  metrics jsonb NOT NULL,
  source text,
  created_at timestamptz DEFAULT now(),
  UNIQUE (ticker, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_financials_ticker ON financial_statements (ticker);

-- Financials RLS: public read; writes restricted to admins (split policies)
ALTER TABLE financial_statements ENABLE ROW LEVEL SECURITY;
CREATE POLICY financials_select_public ON financial_statements
  FOR SELECT
  USING (true);

CREATE POLICY financials_insert_admin ON financial_statements
  FOR INSERT
  WITH CHECK (is_admin(auth.uid()::uuid));

CREATE POLICY financials_update_admin ON financial_statements
  FOR UPDATE
  USING (is_admin(auth.uid()::uuid))
  WITH CHECK (is_admin(auth.uid()::uuid));

CREATE POLICY financials_delete_admin ON financial_statements
  FOR DELETE
  USING (is_admin(auth.uid()::uuid));

-- =================================================================
-- Time-series / Technicals (typed columns per your requested fields)
--    - daily resolution assumed; change ts -> timestamptz for intraday
-- =================================================================
CREATE TABLE IF NOT EXISTS technical_daily (
  ticker text NOT NULL REFERENCES stocks (ticker),
  ts date NOT NULL,                 -- use timestamptz for intraday
  close numeric NOT NULL,
  macd numeric,
  macd_signal numeric,
  rsi numeric,
  upper_band numeric,
  lower_band numeric,
  buy_signal boolean DEFAULT false,
  sell_signal boolean DEFAULT false,
  source text,
  created_at timestamptz DEFAULT now(),
  PRIMARY KEY (ticker, ts)
);

CREATE INDEX IF NOT EXISTS idx_technical_ticker_ts_desc ON technical_daily (ticker, ts DESC);

-- Technical_daily RLS: public read; admin writes only (split policies)
ALTER TABLE technical_daily ENABLE ROW LEVEL SECURITY;
CREATE POLICY technical_daily_select_public ON technical_daily
  FOR SELECT
  USING (true);

CREATE POLICY technical_daily_insert_admin ON technical_daily
  FOR INSERT
  WITH CHECK (is_admin(auth.uid()::uuid));

CREATE POLICY technical_daily_update_admin ON technical_daily
  FOR UPDATE
  USING (is_admin(auth.uid()::uuid))
  WITH CHECK (is_admin(auth.uid()::uuid));

CREATE POLICY technical_daily_delete_admin ON technical_daily
  FOR DELETE
  USING (is_admin(auth.uid()::uuid));

-- =================================================================
-- CMS: pages & research_posts
-- =================================================================
CREATE TABLE IF NOT EXISTS pages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text UNIQUE,
  title text,
  body jsonb,
  is_public boolean DEFAULT true,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

ALTER TABLE pages ENABLE ROW LEVEL SECURITY;
CREATE POLICY pages_select_public ON pages
  FOR SELECT
  USING (is_public = true);

CREATE POLICY pages_insert_admin ON pages
  FOR INSERT
  WITH CHECK (is_admin(auth.uid()::uuid));

CREATE POLICY pages_update_admin ON pages
  FOR UPDATE
  USING (is_admin(auth.uid()::uuid))
  WITH CHECK (is_admin(auth.uid()::uuid));

CREATE POLICY pages_delete_admin ON pages
  FOR DELETE
  USING (is_admin(auth.uid()::uuid));

CREATE TABLE IF NOT EXISTS research_posts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  author_id uuid REFERENCES profiles (id),
  title text,
  summary text,
  content jsonb,
  published_at timestamptz,
  status text DEFAULT 'draft',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz
);

ALTER TABLE research_posts ENABLE ROW LEVEL SECURITY;
-- allow authors or admins to SELECT
CREATE POLICY research_posts_select ON research_posts
  FOR SELECT
  USING (author_id = auth.uid() OR is_admin(auth.uid()::uuid));

-- allow authors or admins to INSERT (check author_id)
CREATE POLICY research_posts_insert ON research_posts
  FOR INSERT
  WITH CHECK (author_id = auth.uid() OR is_admin(auth.uid()::uuid));

-- allow authors or admins to UPDATE (use USING + WITH CHECK)
CREATE POLICY research_posts_update ON research_posts
  FOR UPDATE
  USING (author_id = auth.uid() OR is_admin(auth.uid()::uuid))
  WITH CHECK (author_id = auth.uid() OR is_admin(auth.uid()::uuid));

-- allow authors or admins to DELETE
CREATE POLICY research_posts_delete ON research_posts
  FOR DELETE
  USING (author_id = auth.uid() OR is_admin(auth.uid()::uuid));

-- =========================================================
-- Advisory / access notes:
-- =========================================================
-- Add admin(s) (run from server role or SQL editor as a trusted client):
-- INSERT INTO admins (user_id) VALUES ('<admin-uuid>');

-- If you want profiles created automatically when a user signs up,
-- handle that in an auth webhook or server-side function to INSERT into profiles (id = auth_user_id).

-- =========================================================
-- End of fixed trimmed setup script
-- =========================================================
