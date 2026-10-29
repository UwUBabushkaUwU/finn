# Phase 5 · Product and interaction — Antigravity prompts

Three prompts (plus one optional), **one new Antigravity conversation each**. After each, open the site on your phone and send Claude a screenshot.

## The interaction model (FINN's point of view, for the writeup)

- **Two moments, two screens.** *Morning:* the Brief says what changed, ranked. *At the desk:* the Company page answers "can I still trust what management tells me?"
- **Every claim is one tap from its source.** Each number, quote and verdict links to the exact PDF page it came from.
- **FINN says "I don't know" out loud.** "Too early" and "Can't verify" are shown on purpose; that's what makes the rest believable.
- **Research any company from the phone.** Type a ticker; FINN reads its filings in about 4 minutes, shows its progress, and keeps the result as a page you come back to.

---

## 5.1 · The company page

> Read `.agent/rules/finn.md` first. Plan before coding, and describe the screen to me before building.
>
> Build `/c/[ticker]` in `web/`. Data: the `research` rows for that ticker (sections `meta`, `promises`, `guidance_timeline`, `numbers`, `snapshot`, `bull_bear`), the latest `prices` row, and `financials` for the charts. Server components, `revalidate = 300`. Same design language as the Brief: calm, dense, newspaper-like, one accent, phone-first (375 px), light and dark.
>
> **Top to bottom:**
>
> 1. **Header:** ticker (bold), name, sector; latest close and day % (if in `prices`); one quiet line "Researched 2h ago · 5 earnings calls · FY26 annual report".
>
> 2. **"Did management deliver?" (the hero).**
>    - Map the verdicts into five plain groups: **Kept** (delivered, likely_delivered, ended + ahead), **Broken** (missed, likely_missed, partly), **In progress** (on_track, ahead, behind), **Too early** (pending), **Can't verify** (unverifiable, not_judged). Mark "likely_*" with a hollow badge and the word "likely".
>    - A single horizontal **segmented bar** showing the counts, with a legend in words ("3 kept · 1 broken · 5 in progress · 4 too early · 2 can't verify"). Colour: kept = good, broken = critical, behind = warning, the rest neutral.
>    - The post-override **read** (2 sentences) under the bar.
>    - The **promise list, ordered by what an investor needs first**: Broken, then Behind, then Kept/Ahead, then On track. "Too early" and "Can't verify" go in one collapsed row at the bottom ("6 more: too early or can't verify").
>    - Each row: the promise (≤15 words), "said in Q2 FY26", verdict chip, the evidence line, and a revision label if there is one ("cut from 20%"). **Tap to expand:** the verbatim quote in a quote style, the speaker, and a source link "Q2 FY26 call, p.7 ↗" that opens `url#page=7`. For numeric evidence, show its source too (e.g. "Quarterly results, Jun 2026 · screener").
>
> 3. **"How the story changed":** only targets whose guidance was revised. Each as one row: metric and period, then the chain of values by quarter, e.g. `FY27 revenue growth   20% → 20% → 15–18% → 15%`, with the quarter under each value. Hide the section if there are no revisions.
>
> 4. **The numbers.**
>    - Four tiles: TTM revenue, TTM PAT (with YoY), operating margin (latest), debt-to-equity. Lenders: replace margin and D/E with what `numbers` provides and note "lender".
>    - One small chart: the last 12 quarters of revenue as bars, with operating margin % as a line on a second axis. Hand-drawn SVG, no chart library; label the latest value only.
>    - **Flags:** only triggered flags, each a row with its numbers, e.g. "Cash conversion 57% over 3 yrs (CFO ₹6,744 cr vs PAT ₹11,906 cr)". If none: "No balance-sheet or cash flags."
>
> 5. **What the business is:** `what_it_does`, then segments as a single stacked bar with shares (if present), then customers and markets. Footer: "From the FY26 annual report, p.12, 45 ↗".
>
> 6. **Bull vs bear:** two blocks, each with 2–3 points. Each point ends with small source chips for its ids. Tapping a chip scrolls to the promise, number or segment it refers to (give those elements ids), or opens the PDF page if it's a quote.
>
> 7. **Sources:** collapsed list of every document used (kind, period, link). One line: "FINN uses only company documents: earnings-call transcripts, presentations, the annual report and reported financials. No news or broker research."
>
> If the ticker has no research: show the company name if we know it and a "Research this company" button (we'll wire it in 5.2; for now it can be disabled).
>
> On the Brief, make each card's ticker a link to `/c/[ticker]`.
>
> Run locally. Screenshots at 375 px of `/c/DIXON` (whole page, dark mode), the expanded promise T12, and `/c/BAJFINANCE` (light). Commit and push.

**You:** open `/c/DIXON` on your phone and send Claude a screenshot.

---

## 5.2 · Research tab and research-any-ticker

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> **1. Navigation:** a bottom tab bar on every page: **Brief** · **Research** · **Settings**. Thumb-reachable, respects the iPhone safe area, active tab marked.
>
> **2. `/research`:**
> - At the top, an input: "Research any NSE company: type a ticker". Uppercase it and validate (letters, digits, `&`, `-`, max 20 chars).
> - Below, a list of researched companies (from `research_jobs` with status `done`, joined with `research` `meta` and `promises` counts). Each row: ticker, name, and a tiny version of the segmented promises bar with "3 kept · 1 broken". Portfolio companies first, then the rest. Tap → `/c/[ticker]`.
>
> **3. Starting research:** `POST /api/research` (Next.js route handler, server only):
> - If `research_jobs` shows that ticker `done` within the last 7 days, return "ready" and open its page.
> - If it's `queued` or `running`, return its status.
> - Otherwise call GitHub's `workflow_dispatch` for `research.yml` with input `ticker`, using `GH_DISPATCH_TOKEN` (server env only, never `NEXT_PUBLIC_`). Repo `UwUBabushkaUwU/finn`, branch `main`.
> - Basic abuse guard: at most 10 dispatches per hour in total (count recent `research_jobs.requested_at`).
> - The web app never writes to the database; `run.py` creates and updates the job row.
>
> **4. Progress screen** (`/c/[ticker]` while a job is queued or running): poll `research_jobs` every 5 s and show the steps as a checklist with plain words: "Finding filings and transcripts" (corpus) → "Reading earnings calls" (promises extract) → "Checking promises against results" (judge) → "Crunching the numbers" → "Reading the annual report" (snapshot) → "Writing the bull and bear case". Show elapsed time and "Usually about 4 minutes. You can leave; it'll be under Research." When done, load the page. If failed, show the error in plain words (e.g. "screener.in has no data for XYZ") and a "Try again" button.
>
> **5.** Make sure `run.py` sets `requested_at` and `step` values that match these steps, and that a job for an unknown ticker fails cleanly with a readable error.
>
> **6.** Queue research for all 18 portfolio companies: run `run.py --ticker` for each locally, one at a time, so every Brief card's ticker opens a research page.
>
> Tell me when I need to add `GH_DISPATCH_TOKEN` (explain the exact steps). Test the full flow with a ticker that has no research, e.g. `HAVELLS`. Screenshot the progress screen and the finished page. Commit and push.

**You** (Antigravity will remind you):

1. GitHub → your profile picture → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**. Name: `finn-dispatch`. Expiration: 30 days. Repository access: **Only select repositories** → `finn`. Permissions → Repository → **Actions: Read and write**. Generate, then copy the token.
2. Vercel → your project → **Settings** → **Environment Variables** → add `GH_DISPATCH_TOKEN` with that value → Save → **Deployments** → **Redeploy** the latest.

**You:** on your phone, go to Research, type `HAVELLS`, and send Claude a screenshot of the progress screen.

---

## 5.3 · Settings, install as an app, polish

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> **1. `/settings`:** edit the `settings` row (id 1) with the publishable key (RLS allows anon update on that row):
> - Volume spike: "Alert when volume is above [2.0]× its [20]-day average" (stepper or slider, 1.5–5×).
> - Price move: "Alert when a stock moves more than [5]% in a day" (1–15%).
> - Filing alerts: toggles for each category in `alert_categories` (results, M&A, management change, fund raise, litigation, credit rating, pledging, plus dividend, capex, insider trading off by default).
> - Save button with a clear confirmation: "Saved. New alerts use this from the next check (within 30 min)."
> - Under it, "Your portfolio": the 18 companies as a simple list (read-only; note "Edit in portfolio.yaml" for now).
>
> **2. Install as an app (PWA):** `manifest.webmanifest` (name FINN, short_name FINN, standalone display, theme colours matching light and dark), icons 192 px and 512 px plus an Apple touch icon (a simple serif "F" on the background colour, generated as PNGs), `apple-mobile-web-app-capable`, and the status-bar style. No service-worker caching of data (keep it simple and always fresh).
>
> **3. Polish pass across all screens:**
> - Loading skeletons in the same layout (no spinners), and a friendly error state if Supabase is unreachable.
> - Unknown ticker on `/c/[ticker]` → "We don't know XYZ yet" + the research button.
> - Brief: the 24h empty state suggests switching to 7d.
> - Check tap targets ≥ 44 px, no horizontal scroll at 375 px, text contrast in both themes, and that the tab bar never covers content.
> - Page titles and a description meta tag ("FINN: what changed in your portfolio, and whether management delivered").
>
> Screenshots at 375 px: Settings (dark), Research list (light), and the Brief top (light). Commit and push.

**You:** on your phone, open the site → Share → **Add to Home Screen**, then open FINN from the icon and send Claude one screenshot.

---

## 5.4 · Optional, only if there's time: ask a question about a company

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> On `/c/[ticker]`, add an "Ask about [ticker]" box (a question at most 200 characters, e.g. "What did they say about margins?").
>
> - Our Python code doesn't run on Vercel, so use a Next.js route `POST /api/ask` that calls Gemini (`gemini-flash-lite-latest`) directly via REST with `GEMINI_API_KEY` (server env only). Record this as the one exception to the "all LLM calls in llm.py" rule in `finn.md`.
> - The model gets **only** this company's stored facts from its `research` rows: promises with their quotes, verdicts, the guidance timeline, numbers and snapshot, each with an id. Prompt: answer in at most 80 words using only these facts, cite ids, and say "The documents I have don't cover that" if they don't.
> - The route drops any answer whose ids don't exist and shows the cited quotes under the answer with their PDF page links.
> - Cache answers in memory per (ticker, question) for the session; limit to 20 questions per hour in total.
>
> Test with three questions on DIXON (one it can answer, one about margins, one it can't answer, e.g. "Who is the CEO's wife?"). Screenshots. Commit and push.
