# FINN — project rules

Place at: `.agent/rules/finn.md`. Antigravity reads this on every task in this repo.

## What we're building

FINN is a mobile-first investment agent for an Indian public-markets investor.

- **Push:** a ranked brief of exchange filings across a portfolio, plus alerts for unusual end-of-day price and volume moves.
- **Pull:** on-demand research on any NSE ticker, built only from primary sources.

It's a prototype for a build challenge. A thin, working product beats a broad, broken one. Never leave the repo in a state that doesn't run.

## Stack

- **Pipeline:** Python 3.11, run locally and on GitHub Actions. Libraries: `supabase`, `yfinance`, `pandas`, `requests`, `pyyaml`, `python-dotenv`, `google-genai`.
- **Database:** Supabase Postgres. Migrations live in `supabase/migrations/` as numbered `.sql` files.
- **Website:** Next.js (App Router) + TypeScript + Tailwind in `web/`, deployed to Vercel, installable as a PWA.
- **LLM:** Google Gemini via the `google-genai` SDK. Model ids come from `pipeline/portfolio.yaml` (`models.bulk`, `models.reasoning`), never hard-coded.

## Folder layout

```
pipeline/     data jobs: fetch, classify, enrich, alerts; llm.py, db.py, config.py
research/     pull-side engine (primary sources only)
web/          Next.js app
supabase/     migrations
.github/workflows/   filings.yml, eod.yml, research.yml
docs/ai-history/     exported AI conversations
```

Don't create new top-level folders without asking.

## Hard rules

1. **Secrets come only from environment variables.** The names are exactly: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SEARCH_API_KEY`. Load `.env` with `python-dotenv` locally. Never print, log, hard-code or commit a key value. `SUPABASE_SECRET_KEY` must never be referenced anywhere under `web/`.
2. **Every LLM call goes through `pipeline/llm.py`.** It picks the model by task and caches results in the `llm_cache` table keyed on a hash of (model, prompt version, input). No other file calls Gemini directly.
3. **Research uses primary sources only:** annual reports, concall transcripts, exchange filings and screener.in's financial tables. No web search, news, broker notes, or the model's own background knowledge. Nothing in `research/` may import the search client. Every claim in research output carries a source reference (document and page or quarter).
4. **Scripts are idempotent.** Re-running any script must never create duplicate rows. Use upserts with natural keys.
5. **Be polite to data sources.** Send a browser-like User-Agent, wait at least 1 second between requests to NSE, BSE and screener.in, retry with exponential backoff (max 3 tries), and cache raw downloads.
6. **Tickers are NSE symbols** (`LT`, `INFY`) everywhere in the database and code. Add `.NS` only at the point of calling yfinance.
7. **Times are stored in UTC** (`timestamptz`) and displayed in IST (Asia/Kolkata).
8. **Ask before adding a dependency.** Pin versions in `requirements.txt` / `package.json`.

## How to work

- **Plan first.** For any task touching more than two files, write a short plan and wait for approval before coding.
- **Run what you build.** After implementing, run the script or open the page and show the actual output. Never say a task is done without running it.
- **Stay in scope.** Only touch files the task needs. Mention anything else you notice instead of fixing it.
- **Small pieces.** Functions under ~50 lines, type hints, `logging` for diagnostics. CLI scripts end with a short human-readable summary.
- **Fail loudly, degrade gracefully.** One bad ticker or filing logs an error and the run continues; the script exits non-zero only if everything failed.
- **Commit after each working task** with a conventional message (`feat(pipeline): fetch EOD prices`).
