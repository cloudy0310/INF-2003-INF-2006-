-- =========================================================
-- FULL RESET + SETUP SCRIPT for Supabase (Postgres)
-- WARNING: destructive. Drops the entire public schema and everything in it.
-- This variant: only users with users.is_admin = true may INSERT/UPDATE/DELETE on content.
-- =========================================================

-- Option: Full schema reset (recommended for a true "drop everything" state)
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

-- Restore default privileges on public schema (optional)
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

-- Recreate extensions (pgcrypto for gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Begin DDL creation
BEGIN;

-- -----------------------
-- Users (added is_admin flag)
-- -----------------------
CREATE TABLE users (
  user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username        TEXT NOT NULL UNIQUE,
  email           TEXT NOT NULL UNIQUE,
  is_admin        BOOLEAN NOT NULL DEFAULT false, -- <--- new flag
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at   TIMESTAMPTZ
);

-- -----------------------
-- Watchlists
-- -----------------------
CREATE TABLE watchlists (
  watchlist_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  description     TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------
-- Watchlist stocks
-- -----------------------
CREATE TABLE watchlist_stocks (
  watchlist_id    UUID NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
  ticker          TEXT NOT NULL,
  added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (watchlist_id, ticker)
);

-- -----------------------
-- Companies
-- -----------------------
CREATE TABLE companies (
  ticker                TEXT PRIMARY KEY,
  name                  TEXT,
  short_name            TEXT,
  exchange              TEXT,
  market                TEXT,
  country               TEXT,
  region                TEXT,
  city                  TEXT,
  address1              TEXT,
  phone                 TEXT,
  website               TEXT,
  ir_website            TEXT,
  sector                TEXT,
  industry              TEXT,
  industry_key          TEXT,
  long_business_summary TEXT,
  full_time_employees   INTEGER,
  founded_year          INTEGER,
  market_cap            NUMERIC(30,2),
  float_shares          BIGINT,
  shares_outstanding    BIGINT,
  beta                  NUMERIC(10,6),
  book_value            NUMERIC(20,6),
  dividend_rate         NUMERIC(20,8),
  dividend_yield        NUMERIC(10,8),
  last_dividend_date    DATE,
  last_split_date       DATE,
  last_split_factor     TEXT,
  logo_url              TEXT,
  esg_populated         BOOLEAN,
  created_at            TIMESTAMPTZ DEFAULT now(),
  updated_at            TIMESTAMPTZ DEFAULT now(),
  raw_yfinance          JSONB
);

-- -----------------------
-- Company officers
-- -----------------------
CREATE TABLE company_officers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker        TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  title         TEXT,
  year_of_birth INTEGER,
  age           INTEGER,
  fiscal_year   INTEGER,
  total_pay     NUMERIC(20,2),
  extra         JSONB,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- -----------------------
-- Financials
-- -----------------------
CREATE TABLE financials (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker               TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
  period_end           DATE NOT NULL,
  period_type          TEXT NOT NULL CHECK (period_type IN ('FY','Q')),
  reported_currency    TEXT,

  revenue              NUMERIC(30,2),
  cost_of_revenue      NUMERIC(30,2),
  gross_profit         NUMERIC(30,2),
  operating_income     NUMERIC(30,2),
  net_income           NUMERIC(30,2),
  eps_basic            NUMERIC(20,6),
  eps_diluted          NUMERIC(20,6),
  ebitda               NUMERIC(30,2),

  gross_margin         NUMERIC(12,8),
  operating_margin     NUMERIC(12,8),
  ebitda_margin        NUMERIC(12,8),
  net_profit_margin    NUMERIC(12,8),

  total_assets         NUMERIC(30,2),
  total_liabilities    NUMERIC(30,2),
  total_equity         NUMERIC(30,2),
  cash_and_equivalents NUMERIC(30,2),
  total_debt           NUMERIC(30,2),

  operating_cashflow   NUMERIC(30,2),
  capital_expenditures NUMERIC(30,2),
  free_cash_flow       NUMERIC(30,2),

  shares_outstanding   BIGINT,
  shares_float         BIGINT,
  market_cap           NUMERIC(30,2),
  price_to_earnings    NUMERIC(18,8),
  forward_pe           NUMERIC(18,8),
  peg_ratio            NUMERIC(18,8),

  revenue_growth       NUMERIC(12,8),
  earnings_growth      NUMERIC(12,8),

  number_of_analysts   INTEGER,
  recommendation_mean  NUMERIC(6,3),

  fetched_at           TIMESTAMPTZ DEFAULT now(),
  raw_json             JSONB
);

CREATE UNIQUE INDEX ux_financials_ticker_period ON financials(ticker, period_end, period_type);

-- -----------------------
-- Content
-- -----------------------
CREATE TABLE content (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  author_id     UUID REFERENCES users(user_id) ON DELETE SET NULL,
  title         TEXT NOT NULL,
  slug          TEXT UNIQUE,
  body          TEXT NOT NULL,
  excerpt       TEXT,
  image_url     TEXT,
  ticker        TEXT REFERENCES companies(ticker) ON DELETE SET NULL,
  tags          TEXT[],
  published_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now(),
  raw_meta      JSONB
);

-- -----------------------
-- Enable Row Level Security and create policies for content
-- Only admin users (users.is_admin = true) may INSERT / UPDATE / DELETE content.
-- (Reads allowed according to the SELECT policy below.)
-- -----------------------
ALTER TABLE content ENABLE ROW LEVEL SECURITY;

-- Allow SELECT on content (adjust as you prefer).
-- Current policy: allow anyone who can connect (authenticated/anon) to SELECT rows.
CREATE POLICY "allow_select_content" ON content
  FOR SELECT
  USING ( true );

-- Allow admin users to INSERT rows
CREATE POLICY "admins_insert_content" ON content
  FOR INSERT
  USING ( (SELECT is_admin FROM users WHERE user_id = auth.uid()::uuid) IS TRUE )
  WITH CHECK ( (SELECT is_admin FROM users WHERE user_id = auth.uid()::uuid) IS TRUE );

-- Allow admin users to UPDATE rows
CREATE POLICY "admins_update_content" ON content
  FOR UPDATE
  USING ( (SELECT is_admin FROM users WHERE user_id = auth.uid()::uuid) IS TRUE )
  WITH CHECK ( (SELECT is_admin FROM users WHERE user_id = auth.uid()::uuid) IS TRUE );

-- Allow admin users to DELETE rows
CREATE POLICY "admins_delete_content" ON content
  FOR DELETE
  USING ( (SELECT is_admin FROM users WHERE user_id = auth.uid()::uuid) IS TRUE );

-- If you also want authors to update their own drafts, uncomment & adjust the policy below:
-- CREATE POLICY "authors_update_own_content" ON content
--   FOR UPDATE
--   USING ( author_id = auth.uid()::uuid )
--   WITH CHECK ( author_id = auth.uid()::uuid );

-- -----------------------
-- Materialized view: latest_financials
-- -----------------------
-- Create the materialized view after the financials table exists
CREATE MATERIALIZED VIEW latest_financials AS
SELECT DISTINCT ON (f.ticker) f.*
FROM financials f
ORDER BY f.ticker, f.period_end DESC;

COMMIT;

-- -----------------------
-- Helpful indexes
-- -----------------------
CREATE INDEX IF NOT EXISTS ix_companies_sector ON companies(sector);
CREATE INDEX IF NOT EXISTS ix_companies_industry ON companies(industry);
CREATE INDEX IF NOT EXISTS ix_financials_ticker_period_end ON financials(ticker, period_end DESC);
CREATE INDEX IF NOT EXISTS ix_content_ticker ON content(ticker);

-- =========================================================
-- Notes & helper SQL
-- =========================================================
-- 1) Promote a user to admin (run with service_role or DB-admin connection):
--    UPDATE users SET is_admin = true WHERE email = 'admin@example.com';
--
-- 2) If you use custom JWT claims (e.g., "role" claim), you can instead write policies
--    that check auth.jwt() ->> 'role' = 'admin'. Example:
--      (auth.jwt() ->> 'role') = 'admin'
--
-- 3) Service role (Supabase server key) bypasses RLS. Use it for backend jobs that
--    must write content even if not performed by an admin user.
--
-- 4) If you want public users to be able to READ only published content, change the SELECT policy to:
--    USING ( published_at IS NOT NULL )
--
-- =========================================================
-- End of reset + setup script (admin-edit-only content)
-- =========================================================

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;

GRANT ALL ON TABLE companies TO service_role;
GRANT ALL ON TABLE company_officers TO service_role;
GRANT ALL ON TABLE financials TO service_role;

-- Create a function that runs after a new auth user is created
create or replace function public.handle_new_auth_user()
returns trigger language plpgsql
as $$
begin
  -- Insert a row into your public.users profile table
  insert into public.users (user_id, email, username, created_at)
  values (NEW.id::uuid, NEW.email, COALESCE(NEW.raw_user_meta->>'username', NEW.email), now())
  on conflict (user_id) do nothing;

  return NEW;
end;
$$;

-- Create the trigger on auth.users (fires for each new auth user)
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_auth_user();

-- Automatically create a profile row when a new user signs up
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (user_id, email, username)
  VALUES (NEW.id, NEW.email, split_part(NEW.email, '@', 1))
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "allow_users_select_own_profile" ON public.users
  FOR SELECT
  USING ( user_id = auth.uid()::uuid );

-- -----------------------
-- News YM Review
-- -----------------------

create table if not exists public.news_articles (
  article_id     text primary key,                  
  title          text            not null,
  canonical_url  text            not null unique,   -- publisher URL
  source         text,
  author         text,
  snippet        text,                              -- short summary/excerpt
  content        text,                              -- Fulltext
  image_url      text,
  published_at   timestamptz,
  fetched_at     timestamptz    not null default now(),
  score          double precision,
  tags           text[]          default '{}',
  raw            jsonb
);

alter table public.news_articles
  add column if not exists day date generated always as (date(published_at)) stored;

create index if not exists news_articles_published_idx on public.news_articles (published_at desc);
create index if not exists news_articles_day_idx       on public.news_articles (day desc);
create index if not exists news_articles_source_idx    on public.news_articles (source);

create index if not exists news_articles_search_idx on public.news_articles
using gin (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(snippet,'')));

-- -----------------------
-- News Summary
-- -----------------------

create table if not exists public.news_daily_summary (
  day              date primary key,
  summary          text not null,        -- paragraph: recent developments
  outlook          text not null,        -- paragraph: cautious outlook
  sentiment_score  double precision,
  article_ids      text[] not null,      -- references news_articles.article_id
  created_at       timestamptz not null default now()
);


-- -----------------------
-- stock prices
-- -----------------------
create table stock_prices (
    ticker text not null,                      -- Partition key (symbol)
    date date not null,                        -- Sort key (date)
    
    -- OHLCV
    open numeric(12,4),
    high numeric(12,4),
    low numeric(12,4),
    close numeric(12,4),
    volume bigint,
    
    -- Technical Indicators
    bb_sma_20 numeric(12,4),
    bb_upper_20 numeric(12,4),
    bb_lower_20 numeric(12,4),
    rsi_14 numeric(8,4),
    macd numeric(12,4),
    macd_signal numeric(12,4),
    macd_hist numeric(12,4),
    buy_signal boolean default false,
    sell_signal boolean default false,

    -- Timestamps
    created_at timestamp with time zone default now(),

    -- Composite primary key (mimics DynamoDB pk+sk)
    primary key (ticker, date)
);
