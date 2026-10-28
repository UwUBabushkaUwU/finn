# Phase 1 · Data plumbing — Antigravity prompts

Run these in order, **one new Antigravity conversation per prompt**. After each one works: commit, then export the conversation to `docs/ai-history/`.

**Before prompt 1.1:** put `finn.md` in `.agent/rules/` and `portfolio.yaml` in `pipeline/`, then commit them.

---

## 1.1 · Skeleton, database schema, seed

> Read `.agent/rules/finn.md` and `pipeline/portfolio.yaml` first. Plan before coding.
>
> Set up the Python side of the project:
>
> 1. `requirements.txt` with pinned versions of: supabase, yfinance, pandas, requests, pyyaml, python-dotenv, google-genai.
> 2. `pipeline/config.py`: loads `.env` (if present) and `pipeline/portfolio.yaml`; exposes the portfolio tickers, research tickers, alert defaults and model ids.
> 3. `pipeline/db.py`: a Supabase client built from `SUPABASE_URL` and `SUPABASE_SECRET_KEY`, plus small helpers `upsert(table, rows, on_conflict)` and `select(table, **filters)`.
> 4. `supabase/migrations/001_init.sql` creating these tables:
>    - `companies`: ticker (text, primary key), name, sector, size, in_portfolio (bool), is_research (bool), created_at.
>    - `prices`: ticker (references companies), date, open, high, low, close, volume (bigint), pct_change, vol_avg_20, vol_ratio. Primary key (ticker, date).
>    - `filings`: id (text, primary key, the exchange's own id or a hash of ticker + time + subject), ticker, exchange, filed_at (timestamptz), subject, description, attachment_url, raw (jsonb, the original record), category, priority, summary, enrichment (jsonb), processed_at, created_at. Index on (ticker, filed_at desc) and on filed_at desc.
>    - `alerts`: id (bigserial), ticker, kind (`volume_spike` / `price_move` / `material_filing`), message, value, threshold, filing_id (nullable), trigger_date, seen (bool, default false), created_at. Unique on (ticker, kind, trigger_date, filing_id) so re-runs don't duplicate.
>    - `settings`: a single row with id = 1: volume_multiple, volume_lookback_days, price_move_pct, digest_window_hours, alert_categories (text[]), updated_at.
>    - `research`: ticker, section, content (jsonb), sources (jsonb), model, generated_at. Primary key (ticker, section).
>    - `llm_cache`: key (text, primary key), task, model, output (jsonb), created_at.
>
>    Enable row-level security on every table. Add read-only (select) policies for the `anon` role on companies, prices, filings, alerts, settings and research; also allow `anon` to update the settings row. No public access at all to `llm_cache`.
> 5. `pipeline/seed.py`: upserts every company from the YAML (portfolio and research) into `companies`, and the alert defaults into `settings` row 1. Safe to run repeatedly.
>
> Don't run the SQL yourself. When the files are ready, tell me, and I'll paste the migration into the Supabase SQL editor. Then run `python -m pipeline.seed` and show me the row counts.

**You:** open Supabase → SQL Editor → paste `001_init.sql` → Run. Then tell Antigravity it's done so it runs the seed. Expect 22 companies and 1 settings row.

---

## 1.2 · End-of-day prices

> Read `.agent/rules/finn.md` first.
>
> Write `pipeline/fetch_prices.py`:
>
> - Download daily OHLCV for every company in the `companies` table (portfolio and research) from yfinance, using `<ticker>.NS`, in one batched download. Default history: 90 calendar days; accept `--days N`.
> - For each ticker and date compute: `pct_change` = close vs previous close (%), `vol_avg_20` = mean volume of the **previous** 20 trading days (excluding that day), `vol_ratio` = volume ÷ vol_avg_20. Leave them null where there isn't enough history.
> - Upsert into `prices` on (ticker, date). Convert numpy types to plain Python so the Supabase client accepts them.
> - If a ticker returns no data, log it and carry on.
> - End with a summary: tickers fetched, rows upserted, tickers that failed, and the latest date found.
>
> Run it with defaults. Then show me the last 3 rows for LT and SUZLON, and list any ticker whose latest vol_ratio is above 2 or whose latest |pct_change| is above 5.

**Check:** the latest date should be the last trading day. LT should show a large positive move around 28 Oct.

---

## 1.3 · Exchange filings

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> Write `pipeline/fetch_filings.py` to pull corporate announcements from NSE for every portfolio company.
>
> 1. Spend at most 15 minutes checking whether the `dalal` package's `announcements()` works for one symbol (e.g. LT) and returns the attachment link. If it does, ask me before adding it as a dependency.
> 2. Otherwise call NSE directly: open a `requests.Session` with browser-like headers, visit `https://www.nseindia.com` first to get cookies, then call the corporate-announcements API (`/api/corporate-announcements?index=equities&symbol=<SYM>&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY`). Inspect a real response and map its fields; don't guess field names.
> 3. Map each announcement to the `filings` table: a stable `id` (NSE's own id if there is one, else a SHA-256 of ticker + timestamp + subject), `exchange = 'NSE'`, `filed_at` (convert IST → UTC), subject, description, the full PDF attachment URL, and the original record in `raw`. Leave category, priority, summary and enrichment null; classification comes later.
> 4. Default window: last 7 days; accept `--days N` and `--ticker SYM`.
> 5. Wait at least 1 second between symbols; retry with backoff; if NSE returns 401/403, refresh the session cookies once and retry.
> 6. Upsert on `id`. End with a summary: filings per ticker, total new vs already present, and any tickers that failed with the HTTP status.
>
> Run it for all tickers. Show the summary, then the 5 most recent filings for HOMEFIRST and BRITANNIA (time in IST, subject, attachment URL).

**You:** open two or three of the attachment URLs and compare them with the announcements on the NSE website for the same company.

---

## 1.4 · GitHub Actions workflows

> Read `.agent/rules/finn.md` first.
>
> Create two GitHub Actions workflows:
>
> - `.github/workflows/eod.yml`: runs `python -m pipeline.fetch_prices --days 10` on weekdays at 10:45 UTC (4:15 PM IST, after market close).
> - `.github/workflows/filings.yml`: runs `python -m pipeline.fetch_filings --days 2` every 30 minutes from 03:30 to 13:30 UTC on weekdays (9 AM–7 PM IST).
>
> Both: also triggerable manually (`workflow_dispatch`), Python 3.11, pip caching, `timeout-minutes: 15`, and the env vars `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SEARCH_API_KEY` from repository secrets. Don't add any other secrets.
>
> Commit and push. Tell me when to trigger them.

**You:** on GitHub, open the **Actions** tab → pick each workflow → **Run workflow**. Open the run and read the summary at the end of the log.

**This is the most important check in phase 1.** If `fetch_filings` works on your laptop but fails or returns 0 filings on GitHub Actions, NSE is blocking cloud servers. Use prompt 1.5.

---

## 1.5 · Only if NSE fails on GitHub Actions

> `fetch_filings` works locally but on GitHub Actions it fails with: [paste the error / status from the Actions log].
>
> Add BSE as a fallback source. Use BSE's public announcements API (it needs each company's BSE scrip code: add a `bse_code` to every company in `portfolio.yaml`, and to `companies` via a new migration `002_bse_code.sql`). Keep the same `filings` mapping with `exchange = 'BSE'`. Add a `--source nse|bse|auto` flag, where `auto` tries NSE and falls back to BSE per ticker. Run it with `--source bse` locally and show the same HOMEFIRST and BRITANNIA output as before.

Then push, and set the workflow to `--source auto`.

---

## Phase 1 is done when

- Supabase `prices` has ~60 trading days for all 22 companies.
- Supabase `filings` has the last week of announcements for all 18 portfolio companies.
- Both workflows have completed at least one successful run on GitHub Actions.
- You've spot-checked five filings against the NSE website.
