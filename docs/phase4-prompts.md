# Phase 4 · Research engine (pull side) — Antigravity prompts

Three prompts, **one new Antigravity conversation each**. Paste, approve the plan, send Claude the final message.

**The goal:** for *any* NSE ticker, FINN reads the company's own documents and answers "what did management promise over the last four quarters, and did they deliver?", plus a compact snapshot and a bull/bear case. Everything is cited to a document and page.

**The discipline (from the brief):** primary sources only. Concall transcripts, investor presentations, annual reports, and screener.in's financial tables (which are compiled from the company's own filings). No news, no broker notes, no web search, no screener "AI summary" or "notes", and no model background knowledge.

---

## 4.1 · Collect the documents for any ticker

> Read `.agent/rules/finn.md` first. Plan before coding. Ask me before adding `beautifulsoup4`.
>
> Build `research/build_corpus.py --ticker SYM`. It must work for **any** NSE ticker, not just the demo set.
>
> **1. New migration `supabase/migrations/002_research.sql`** (I'll run it in Supabase myself):
> - `documents`: id (text PK = sha256 of url), ticker, kind (`transcript` / `presentation` / `annual_report`), period (e.g. `Q2 FY27`, `FY26`), event_date (date), url, pages (jsonb: list of page texts), page_count, text_ok (bool), fetched_at.
> - `financials`: ticker (PK), basis (`consolidated` / `standalone`), tables (jsonb), fetched_at.
> - `research_jobs`: ticker (PK), status (`queued` / `running` / `done` / `failed`), step (text), error (text), requested_at, started_at, finished_at.
> - Same RLS pattern as 001: anon can select from `financials` and `research_jobs`, and can insert into `research_jobs` with status `queued` (that's how the website will request research later). No anon access to `documents`.
>
> **2. Fetch the screener.in company page.** Try `https://www.screener.in/company/<SYM>/consolidated/` first; if its quarterly table is empty, use `/company/<SYM>/`. Browser-like headers, at least 2 seconds between requests to screener, retry with backoff. Inspect the real HTML; don't guess the structure.
>
> **3. Parse the financial tables** into `financials.tables`: quarterly results (all ~13 quarters), annual profit & loss, balance sheet, cash flow, ratios. Keep each table generic as `{columns: [...period labels...], rows: [{label, values: [...]}]}` with numbers as floats (strip commas and %), exactly as the row labels appear. **Don't hard-code row names**: banks and NBFCs use different rows (Financing Profit, Financing Margin %, etc.), and the code must handle both.
>
> **4. Parse the Documents section.**
> - Concalls: for each date entry, take only the **Transcript** and **PPT** links. **Never** use screener's "AI summary", "Notes" or anything screener itself wrote: that's secondary content.
> - Annual reports: the most recent one only.
> - Map each concall date to the quarter it discusses, using India's April–March fiscal year: a call in Jul–Aug discusses Q1, Oct–Nov Q2, Jan–Feb Q3, Apr–May Q4. Example: a call on 23 Oct 2026 is `Q2 FY27`; a call on 5 May 2026 is `Q4 FY26`.
>
> **5. Download and extract text** for the **5 most recent transcripts**, the presentations for the same quarters, and the latest annual report. pypdf, page by page, into `documents.pages`. If a PDF gives fewer than 200 characters per page on average, it's probably scanned: set `text_ok = false` (we'll send the PDF itself to Gemini later). Skip any document already in `documents`. Annual reports can be 300+ pages, so store them, but cap at 400 pages.
>
> **6.** End with a coverage summary: basis used, quarters in the quarterly table, and every document found (kind, period, pages, text_ok), plus anything missing.
>
> Run it for PERSISTENT, BAJFINANCE, DIXON, KAYNES, and one company we didn't pick: **TITAN**. Show the coverage summaries. Commit and push.

**You:** when Antigravity says the migration is ready, paste `002_research.sql` into the Supabase SQL Editor and run it, same as before.

**Send Claude:** the five coverage summaries.

---

## 4.2 · Promised vs. delivered (the hero feature)

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> Build `research/promises.py --ticker SYM`. Three steps: **extract** (cheap model, once per transcript), **verify** (Python), **judge** (strong model, once per company).
>
> **Step 1 · Extract** (task `"bulk"`, one call per transcript, cached by document id + prompt version). Send the whole transcript text with page markers (`[p.7]`); if `text_ok` is false, send the PDF instead. Save as `research/prompts/claims_v1.txt`:
>
> ```
> You read the transcript of an Indian listed company's earnings call for {period}. Extract what management committed to and what they reported. Use only this transcript. Ignore anything said by analysts except as context for a management answer.
>
> Return JSON:
> {
>  "guidance": [ {
>    "metric": a short lowercase name, e.g. "revenue growth", "ebitda margin", "capex", "order book", "aum growth", "credit cost", "plant commissioning",
>    "statement": what management committed to, in at most 20 words,
>    "target": {"value": number or null, "low": number or null, "high": number or null, "unit": "%", "₹ cr", "date", etc., "direction": "up" | "down" | "flat" | null},
>    "applies_to": the period the target is for, as said or clearly implied, e.g. "FY27", "H2 FY27", "Q3 FY27", "next 2-3 years",
>    "firmness": "explicit" if it has a number or a date, "soft" if it is directional ("we expect improvement"),
>    "update_of_earlier": true if management is restating, raising, cutting or delaying an earlier target, else false,
>    "quote": the exact words from the transcript, copied character for character, at most 40 words,
>    "speaker": name and title as printed,
>    "page": page number
>  } ],
>  "reported": [ {
>    "metric": as above,
>    "value": number, "unit": "...",
>    "period": the period the figure is for,
>    "quote": exact words, at most 30 words,
>    "page": page number
>  } ]
> }
>
> "reported" is for figures management states for the period that are not in a standard profit and loss statement: order book, AUM, volumes, capacity utilisation, segment revenue, customer count, and so on.
> Include only commitments about the company's own future performance. Skip pleasantries, industry outlook and generic statements like "we remain confident".
> If the transcript has no guidance, return empty lists. Never invent a quote.
> ```
>
> **Step 2 · Verify (Python, no LLM).** For every quote, check that it really appears on its page: normalise whitespace, case and quote characters, then require an exact substring match, or a match ≥ 90% with `difflib` over a sliding window. Drop unverified items and log how many. This is FINN's guard against made-up quotes.
>
> Then build the **guidance timeline**: group guidance by (metric, applies_to) across quarters, so a target that moved shows as e.g. "FY27 revenue growth: 20% (Q2 FY26) → 20% (Q3) → 15–18% (Q4) → 15% (Q1 FY27)". Python only.
>
> **Step 3 · Judge** (task `"reasoning"`, one call per company, cached on a hash of its inputs). Give it: the deduplicated guidance list (each with an id, e.g. `G7`), the timeline, the `reported` figures (ids `R1…`), and the quarterly table **with growth already computed in Python**: QoQ and YoY for every row, H1 YoY, and the trailing-four-quarter total vs the previous four (ids `N1…` for each number). Save as `research/prompts/verdicts_v1.txt`:
>
> ```
> You are checking whether an Indian listed company's management delivered on what they said over the last four quarters. You are given their guidance (G ids), figures management later reported (R ids), and financial results with growth rates already calculated (N ids). Use only these. Do not calculate new numbers. Do not use outside knowledge about the company.
>
> For each guidance item worth judging (skip duplicates and trivial items; merge restatements of the same target into one, keeping the earliest id and noting revisions), return:
> {"id": "G..", "promise": at most 15 words, "made_in": period first stated,
>  "verdict": "delivered" | "missed" | "partly" | "on_track" | "behind" | "revised_down" | "revised_up" | "unverifiable",
>  "evidence": "at most 25 words, citing the ids you used, e.g. 'H1 revenue up 12% YoY (N14) vs 20% guided'",
>  "evidence_ids": [...]}
>
> Rules:
> - delivered / missed / partly only if the target period has ended and an N or R figure covers it.
> - on_track / behind if the period is still running and the figures so far point clearly one way.
> - revised_down / revised_up if management itself changed the target before the period ended; say from what to what.
> - unverifiable if no provided figure measures it. Never guess.
> - Soft guidance ("margins should improve") counts as delivered only if the direction clearly happened.
>
> Then return "read": 2 sentences on what the pattern says about management's guidance (for example: conservative and beaten, consistently optimistic, or quietly walked back), citing ids.
>
> Return JSON: {"verdicts": [...], "read": "..."}
> ```
>
> Validate: every evidence id must exist in the inputs; if not, set that verdict to `unverifiable`. **Counts are computed in Python**, not by the model: e.g. "9 promises · 4 delivered · 2 missed · 1 revised down · 2 unverifiable".
>
> Save to the `research` table: section `promises` (verdicts, read, counts, and every cited item with its quote, document, period and page so the screen can show the source), and section `guidance_timeline`.
>
> Run it for PERSISTENT, BAJFINANCE, DIXON, KAYNES and TITAN. Show, for each: quotes extracted vs verified, the counts line, and the full verdict list for PERSISTENT and DIXON with evidence. Commit and push.

**Send Claude:** that output. I'll spot-check a few verdicts against the transcripts.

---

## 4.3 · Snapshot, numbers, bull vs bear, and one command for any ticker

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> **1. `research/numbers.py`: Python only, no LLM.** From `financials.tables`, compute and save section `numbers`:
> - **Snapshot:** latest quarter revenue and PAT with YoY, trailing-12-month revenue and PAT, latest operating margin.
> - **Trajectory:** 3-year and 5-year revenue and PAT CAGR from the annual table; operating margin for each of the last 5 years.
> - **Balance sheet:** borrowings, debt-to-equity (borrowings ÷ (equity capital + reserves)), and working-capital or cash-conversion-cycle days from the ratios table if present.
> - **Cash quality:** cash from operations ÷ net profit, summed over the last 3 years.
> - **Flags by rule:** cash conversion < 70%; debt-to-equity > 1 (non-lenders only); margin down ≥ 3 points over 3 years; working-capital days up ≥ 20 over 3 years. Each flag carries the numbers behind it.
> - Every figure keeps its table and column as its source. Skip anything a table doesn't have; never fill gaps. Lenders: skip margin, D/E and cash-conversion rules and note "lender: different metrics".
>
> **2. `research/snapshot.py`: business snapshot.** From the annual report, pick the most relevant pages **by keyword score, no embeddings**: business overview, segment, products, revenue mix, management discussion. Send at most 12 pages to the `"bulk"` model with this prompt (`research/prompts/snapshot_v1.txt`):
>
> ```
> From these pages of an Indian listed company's annual report, describe the business. Use only these pages.
> Return JSON: {"what_it_does": at most 35 words,
>  "segments": [{"name": "...", "share_of_revenue": number or null, "page": n}],
>  "customers_and_markets": at most 25 words or null,
>  "pages_used": [...]}
> If a figure isn't printed, use null. No marketing language.
> ```
>
> **3. `research/bull_bear.py`** (task `"reasoning"`, cached). Input: the promises verdicts and read, the `numbers` section with flags, and the snapshot, each fact with an id. Prompt (`research/prompts/bull_bear_v1.txt`):
>
> ```
> Write the strongest case for and against owning this Indian listed company, using only the facts given (each has an id). Three points each, at most 25 words per point, each citing the ids it rests on. Points must be specific to this company, never generic ("strong management", "macro risks"). If the facts can't support three points on a side, give fewer.
> Return JSON: {"bull": [{"point": "...", "ids": [...]}], "bear": [...]}
> ```
> Drop any point whose ids don't exist.
>
> **4. `research/run.py --ticker SYM`** runs everything in order (`build_corpus` → `promises` → `numbers` → `snapshot` → `bull_bear`), updating `research_jobs` (status, current step, error). One failing step must not erase earlier sections. Save section `meta` with the company name, documents used (kind, period, url), and generated_at. Add `--pending`: process every `research_jobs` row with status `queued`.
>
> **5. `.github/workflows/research.yml`:** `workflow_dispatch` with a `ticker` input (runs `run.py --ticker`), plus a schedule every 10 minutes from 03:30 to 17:30 UTC that runs `run.py --pending`. Same secrets as the other workflows, `timeout-minutes: 30`.
>
> **6. Prove it generalises:** after pushing, tell me to trigger the workflow from GitHub for **ASIANPAINT** (not in our data at all). Then show the job status and the counts line from its `promises` section.
>
> Also run `run.py` locally for PERSISTENT, BAJFINANCE, DIXON, KAYNES and TITAN, and show each one's flags and bull/bear. Commit and push.

**You:** GitHub → Actions → **Research** → **Run workflow** → type `ASIANPAINT` → Run. That's the "we may point it at a company you didn't pick" test from the brief.

**Send Claude:** the local results and the ASIANPAINT run result.
