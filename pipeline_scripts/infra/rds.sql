-- =========================================================
-- RDS PostgreSQL schema (without stock_prices and news_articles)
-- =========================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Drop in reverse dependency order
DROP TABLE IF EXISTS public.watchlist_stocks CASCADE;
DROP TABLE IF EXISTS public.watchlists CASCADE;
DROP TABLE IF EXISTS public.financials CASCADE;
DROP TABLE IF EXISTS public.content CASCADE;
DROP TABLE IF EXISTS public.company_officers CASCADE;
DROP TABLE IF EXISTS public.companies CASCADE;
DROP TABLE IF EXISTS public.users CASCADE;

-- Users
CREATE TABLE public.users (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text UNIQUE,
  email text UNIQUE,
  is_admin boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz
);

-- Companies
CREATE TABLE public.companies (
  ticker text PRIMARY KEY,
  name text,
  short_name text,
  exchange text,
  market text,
  country text,
  region text,
  city text,
  address1 text,
  phone text,
  website text,
  ir_website text,
  sector text,
  industry text,
  industry_key text,
  long_business_summary text,
  full_time_employees numeric,
  founded_year integer,
  market_cap numeric,
  float_shares numeric,
  shares_outstanding numeric,
  beta numeric,
  book_value numeric,
  dividend_rate numeric,
  dividend_yield numeric,
  last_dividend_date date,
  last_split_date date,
  last_split_factor text,
  logo_url text,
  esg_populated boolean,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  raw_yfinance jsonb
);

-- Company officers
CREATE TABLE public.company_officers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker text NOT NULL,
  name text NOT NULL,
  title text,
  year_of_birth integer,
  age integer,
  fiscal_year integer,
  total_pay numeric,
  extra jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  CONSTRAINT company_officers_ticker_fkey
    FOREIGN KEY (ticker) REFERENCES public.companies(ticker) ON DELETE CASCADE
);

-- Content
CREATE TABLE public.content (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  author_id uuid,
  title text NOT NULL,
  slug text UNIQUE,
  body text NOT NULL,
  excerpt text,
  image_url text,
  ticker text,
  tags text[],
  published_at timestamptz,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  raw_meta jsonb,
  content_type text DEFAULT 'analysis'
    CHECK (content_type = ANY (ARRAY[
      'news','analysis','education','portfolio_tip','market_update','how_to','opinion'
    ])),
  CONSTRAINT content_ticker_fkey  FOREIGN KEY (ticker)   REFERENCES public.companies(ticker),
  CONSTRAINT content_author_fkey  FOREIGN KEY (author_id) REFERENCES public.users(user_id) ON DELETE SET NULL
);

-- Financials
CREATE TABLE public.financials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker text NOT NULL,
  period_end date NOT NULL,
  period_type text NOT NULL CHECK (period_type = ANY (ARRAY['FY','Q'])),
  reported_currency text,
  revenue numeric,
  cost_of_revenue numeric,
  gross_profit numeric,
  operating_income numeric,
  net_income numeric,
  eps_basic numeric,
  eps_diluted numeric,
  ebitda numeric,
  gross_margin numeric,
  operating_margin numeric,
  ebitda_margin numeric,
  net_profit_margin numeric,
  total_assets numeric,
  total_liabilities numeric,
  total_equity numeric,
  cash_and_equivalents numeric,
  total_debt numeric,
  operating_cashflow numeric,
  capital_expenditures numeric,
  free_cash_flow numeric,
  shares_outstanding numeric,
  shares_float numeric,
  market_cap numeric,
  price_to_earnings numeric,
  forward_pe numeric,
  peg_ratio numeric,
  revenue_growth numeric,
  earnings_growth numeric,
  number_of_analysts integer,
  recommendation_mean numeric,
  fetched_at timestamptz DEFAULT now(),
  raw_json jsonb,
  CONSTRAINT financials_ticker_fkey FOREIGN KEY (ticker) REFERENCES public.companies(ticker) ON DELETE CASCADE
);

-- Watchlists
CREATE TABLE public.watchlists (
  watchlist_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  name text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT watchlists_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE
);

-- Watchlist stocks
CREATE TABLE public.watchlist_stocks (
  watchlist_id uuid NOT NULL,
  ticker text NOT NULL,
  added_at timestamptz NOT NULL DEFAULT now(),
  allocation numeric NOT NULL DEFAULT 0 CHECK (allocation >= 0::numeric),
  PRIMARY KEY (watchlist_id, ticker),
  CONSTRAINT watchlist_stocks_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES public.watchlists(watchlist_id) ON DELETE CASCADE,
  CONSTRAINT watchlist_stocks_ticker_fkey      FOREIGN KEY (ticker)       REFERENCES public.companies(ticker)      ON DELETE CASCADE
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_companies_sector_industry ON public.companies (sector, industry);
CREATE INDEX IF NOT EXISTS idx_content_ticker_published ON public.content (ticker, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_financials_ticker_period ON public.financials (ticker, period_end DESC);
CREATE INDEX IF NOT EXISTS idx_watchlists_user ON public.watchlists (user_id);
