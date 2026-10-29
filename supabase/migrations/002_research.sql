-- Migration 002: Research schema for FINN
-- Tables: documents, financials, research_jobs

-- 1. documents
create table if not exists documents (
    id text primary key, -- sha256 of url
    ticker text not null,
    kind text not null check (kind in ('transcript', 'presentation', 'annual_report')),
    period text,
    event_date date,
    url text not null,
    pages jsonb not null default '[]'::jsonb,
    page_count integer not null default 0,
    text_ok boolean not null default true,
    fetched_at timestamptz not null default now()
);

create index if not exists idx_documents_ticker on documents (ticker);
create index if not exists idx_documents_ticker_kind_period on documents (ticker, kind, period);
create index if not exists idx_documents_ticker_date on documents (ticker, event_date desc);

-- 2. financials
create table if not exists financials (
    ticker text primary key,
    basis text not null check (basis in ('consolidated', 'standalone')),
    tables jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now()
);

-- 3. research_jobs
create table if not exists research_jobs (
    ticker text primary key,
    status text not null check (status in ('queued', 'running', 'done', 'failed')),
    step text,
    error text,
    requested_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz
);

-- Enable Row Level Security (RLS) on all tables
alter table documents enable row level security;
alter table financials enable row level security;
alter table research_jobs enable row level security;

-- Drop existing policies if any to allow safe re-runs
drop policy if exists "Allow anon select on financials" on financials;
drop policy if exists "Allow anon select on research_jobs" on research_jobs;
drop policy if exists "Allow anon insert queued on research_jobs" on research_jobs;

-- Read-only policies for anon role
create policy "Allow anon select on financials" on financials for select to anon using (true);
create policy "Allow anon select on research_jobs" on research_jobs for select to anon using (true);

-- Allow anon to enqueue research jobs
create policy "Allow anon insert queued on research_jobs" on research_jobs for insert to anon with check (status = 'queued');

-- No anon policies on documents: documents are private to the backend service role

