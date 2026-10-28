-- Migration 001: Initial schema for FINN
-- Tables: companies, prices, filings, alerts, settings, research, llm_cache

-- 1. companies
create table if not exists companies (
    ticker text primary key,
    name text not null,
    sector text,
    size text,
    in_portfolio boolean not null default false,
    is_research boolean not null default false,
    created_at timestamptz not null default now()
);

-- 2. prices
create table if not exists prices (
    ticker text not null references companies(ticker) on delete cascade,
    date date not null,
    open double precision,
    high double precision,
    low double precision,
    close double precision,
    volume bigint,
    pct_change double precision,
    vol_avg_20 double precision,
    vol_ratio double precision,
    primary key (ticker, date)
);

-- 3. filings
create table if not exists filings (
    id text primary key,
    ticker text not null references companies(ticker) on delete cascade,
    exchange text not null,
    filed_at timestamptz not null,
    subject text not null,
    description text,
    attachment_url text,
    raw jsonb not null default '{}'::jsonb,
    category text,
    priority smallint check (priority in (1, 2, 3)),
    summary text,
    enrichment jsonb,
    processed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists idx_filings_ticker_filed_at on filings (ticker, filed_at desc);
create index if not exists idx_filings_filed_at on filings (filed_at desc);
create index if not exists idx_filings_priority_filed_at on filings (priority, filed_at desc);

-- 4. alerts
create table if not exists alerts (
    id bigserial primary key,
    ticker text not null references companies(ticker) on delete cascade,
    kind text not null check (kind in ('volume_spike', 'price_move', 'material_filing')),
    message text not null,
    value double precision,
    threshold double precision,
    filing_id text references filings(id) on delete cascade,
    trigger_date date not null,
    seen boolean not null default false,
    created_at timestamptz not null default now(),
    constraint alerts_unique_event unique nulls not distinct (ticker, kind, trigger_date, filing_id)
);

-- 5. settings
create table if not exists settings (
    id integer primary key default 1 check (id = 1),
    volume_multiple double precision not null default 2.0,
    volume_lookback_days integer not null default 20,
    price_move_pct double precision not null default 5.0,
    digest_window_hours double precision not null default 24.0,
    alert_categories text[] not null default '{}'::text[],
    updated_at timestamptz not null default now()
);

-- 6. research
create table if not exists research (
    ticker text not null references companies(ticker) on delete cascade,
    section text not null,
    content jsonb not null default '{}'::jsonb,
    sources jsonb not null default '[]'::jsonb,
    model text,
    generated_at timestamptz not null default now(),
    primary key (ticker, section)
);

-- 7. llm_cache
create table if not exists llm_cache (
    key text primary key,
    task text not null,
    model text not null,
    output jsonb not null,
    created_at timestamptz not null default now()
);

-- Enable Row Level Security (RLS) on all tables
alter table companies enable row level security;
alter table prices enable row level security;
alter table filings enable row level security;
alter table alerts enable row level security;
alter table settings enable row level security;
alter table research enable row level security;
alter table llm_cache enable row level security;

-- Drop existing policies if any to allow safe re-runs
drop policy if exists "Allow anon select on companies" on companies;
drop policy if exists "Allow anon select on prices" on prices;
drop policy if exists "Allow anon select on filings" on filings;
drop policy if exists "Allow anon select on alerts" on alerts;
drop policy if exists "Allow anon select on settings" on settings;
drop policy if exists "Allow anon update on settings" on settings;
drop policy if exists "Allow anon select on research" on research;

-- Read-only (select) policies for anon role
create policy "Allow anon select on companies" on companies for select to anon using (true);
create policy "Allow anon select on prices" on prices for select to anon using (true);
create policy "Allow anon select on filings" on filings for select to anon using (true);
create policy "Allow anon select on alerts" on alerts for select to anon using (true);
create policy "Allow anon select on settings" on settings for select to anon using (true);
create policy "Allow anon select on research" on research for select to anon using (true);

-- Allow anon to update settings row (id = 1)
create policy "Allow anon update on settings" on settings for update to anon using (id = 1) with check (id = 1);

-- llm_cache has no policies created for anon, denying public access
