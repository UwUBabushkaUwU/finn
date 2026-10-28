# Phase 2 · The filter and a live link — Antigravity prompts

Three prompts, **one new Antigravity conversation each**. Paste, approve the plan, let it run, then send Claude its final message.

At the end you'll have a link that opens on your phone.

---

## 2.1 · Classify filings (FINN's brain)

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> Build the filing classifier.
>
> **1. `pipeline/llm.py`**: the only place that calls Gemini.
> - `call_json(task: str, prompt: str, prompt_version: str) -> dict | list`. `task` is `"bulk"` or `"reasoning"` and picks the model id from `config.MODEL_IDS`.
> - Before calling, check the `llm_cache` table for key = sha256(model + prompt_version + prompt). Return the cached output if found; otherwise call Gemini with JSON output mode, save to the cache, return.
> - Retry on rate-limit errors with backoff (wait 10s, 30s, 60s). Log the number of cache hits vs real calls at the end of a run.
> - First, list the models available to `GEMINI_API_KEY` and confirm the ids in `portfolio.yaml` exist. If they don't, tell me the closest Flash-Lite and Flash ids and update the YAML.
>
> **2. `pipeline/prompts/classify_v1.txt`**: save the prompt below exactly as written. Prompts live in files, not inside Python code. The version (`v1`) is part of the cache key.
>
> **3. `pipeline/classify.py`**:
> - Load filings where `processed_at` is null (accept `--all` to redo everything, `--ticker SYM`).
> - **Rule pre-filter first, no LLM call:** run `select subject, count(*) from filings group by subject` and identify subjects that are always routine paperwork (e.g. newspaper publications, trading window closures, loss of share certificates, SEBI depositories certificates). Set those to `category = 'unclassified'`, `priority = 3`, no headline. **Do not** pre-filter "Analysts/Institutional Investor Meet/Con. Call Updates": it mixes routine meeting notices with concall transcripts. Put the routine subject list in `pipeline/prompts/routine_subjects.txt` so it's easy to edit.
> - Everything else goes to the LLM (task `"bulk"`) in **batches of 20**. Each filing in the batch is sent as `{id, ticker, company name, subject, text}` where text is the `description` field, cut to 1,500 characters.
> - Validate the output: one object per input id, category from the allowed list, priority 1–3. If an item is missing or invalid, retry that item alone once; if it still fails, set priority 2 and headline "Couldn't classify — open the PDF".
> - Save `category`, `priority`, `summary` (= headline) and `processed_at = now()`. Keep `why` inside `enrichment` as `{"why": ...}`.
> - End with a summary: filings processed, how many by rule vs LLM, LLM calls made, cache hits, and counts per priority.
>
> **4.** Add `python -m pipeline.classify` as a step after `fetch_filings` in `.github/workflows/filings.yml`.
>
> Run it on all filings. Then show me: the summary, the routine subject list you chose, and every priority-1 filing (ticker, date in IST, category, headline).
>
> Here is the prompt for `classify_v1.txt`:
>
> ```
> You triage Indian stock-exchange announcements for a professional investor who owns these stocks. Your job is to decide what deserves their attention. Most filings are routine paperwork. Be strict: an investor who sees too many "important" items stops trusting the app.
>
> You get a JSON array of filings. Each has: id, ticker, company, subject (the exchange's label, often vague or wrong), text (the company's own short description).
>
> Return a JSON array with exactly one object per filing, in the same order:
> {"id": "...", "category": "...", "priority": 1, "headline": "...", "why": "..."}
>
> category: one of results, M&A, fund_raise, management_change, litigation, insider_trading, earnings_call, investor_meetings, credit_rating, dividend, bonus_split, capex, press_release, postal_ballot, agm_egm, pledging, unclassified.
>
> priority:
> 1 = Look at it today. It could move the stock or change why someone owns it.
>   - results: the actual quarterly or annual numbers (not a notice of the meeting date)
>   - M&A: any acquisition, merger, demerger, joint venture, or buying or selling a stake
>   - fund_raise: QIP, rights issue, preferential allotment, buyback, or a large debt raise
>   - management_change: a CEO, MD, CFO, chairman, whole-time director or statutory auditor joining or leaving. A resignation by any of them is always priority 1.
>   - litigation: a regulator's order, penalty, tax demand, fraud, insolvency, or a lawsuit with a stated amount or business impact
>   - credit_rating: a downgrade or negative outlook
>   - pledging: a promoter pledge created or increased
>   - press_release: an order, contract or approval whose stated value looks large for this company; a change to guidance; a plant shutdown or disruption
> 2 = Worth knowing. Read when there's time.
>   - notices of the results date, earnings-call schedules, transcripts and recordings, investor presentations, dividends, bonus issues and splits with record dates, capex approvals, rating upgrades, independent-director changes, smaller orders, product launches, promoter or insider buying or selling
> 3 = Routine. Hidden by default.
>   - meeting schedules with investors or analysts, newspaper ads, trading-window closures, procedural AGM / EGM / postal-ballot notices, voting results where resolutions passed, ESOP allotments, compliance certificates, company secretary or compliance officer changes, rating reaffirmations, duplicate share certificates, policy documents, clarifications with nothing new
>
> If unsure between two priorities, pick the less urgent one, unless the filing involves money changing hands, someone at the top leaving, or a regulator.
>
> headline: only for priority 1 and 2; use null for priority 3. At most 16 words. Say what happened, then the number if the text gives one. Don't start with the company name (the app shows it). No words like significant, strong, robust, major. Never "The company announced". Use only numbers that appear in the text. If the text is too vague to say what happened, write "Filing lacks detail — open the PDF" and judge the priority from the subject.
> Good headlines:
>   "CFO Rakesh Shah resigns; Arun Agrawal takes over from 16 Oct"
>   "₹1,240 cr order from NTPC for transmission packages"
>   "Board meets 13 Nov to approve Q2 results"
>   "Q2 results approved; numbers in attached PDF"
>
> why: at most 10 words on why you chose that priority. Internal only.
>
> Use only the text you are given. Do not use outside knowledge about the company.
>
> Filings:
> {filings_json}
> ```

**What to check:** the priority-1 list should be short, roughly 20–40 out of ~270, and should include Home First's results and CFO, Nazara's CFO, and Britannia's management change. Send me the list.

---

## 2.2 · Alerts

> Read `.agent/rules/finn.md` first.
>
> Write `pipeline/alerts.py`. Read thresholds from the `settings` table (row 1), never hard-coded.
>
> - **Price and volume:** for each company's latest row in `prices`, create a `price_move` alert if |pct_change| ≥ `price_move_pct`, and a `volume_spike` alert if vol_ratio ≥ `volume_multiple`. Message examples: "Up 6.2% today" / "Volume 2.7× its 20-day average". `trigger_date` = the price date.
> - **Material filings:** for every filing with priority 1, a category in `alert_categories`, and `filed_at` within the last 48 hours, create a `material_filing` alert with the filing's headline as the message, `filing_id` set, `trigger_date` = filing date in IST.
> - Upsert on (ticker, kind, trigger_date, filing_id) so re-runs never duplicate.
> - Summary at the end: alerts created vs already present, by kind.
>
> Add `python -m pipeline.alerts` as the last step in both `filings.yml` and `eod.yml`.
>
> Run it, show the summary and today's alerts. Then commit and push.

---

## 2.3 · The brief, on your phone

> Read `.agent/rules/finn.md` first. Plan before coding, and show me a description of the screen before building it.
>
> Create the Next.js app in `web/` (App Router, TypeScript, Tailwind, npm). It reads Supabase with `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` only. Put both in `web/.env.local` (gitignored) for local testing.
>
> Build **one screen: the Brief** (`/`). Design it for a phone first (375 px wide); it should also look fine on desktop.
>
> **Purpose:** an investor opens this between meetings and in 20 seconds knows what changed in their portfolio. Show less, not more.
>
> **Layout, top to bottom:**
> 1. **Header:** "FINN", today's date, and a one-line count, e.g. "3 need attention · 11 worth knowing · 42 routine hidden".
> 2. **Time window chips:** 24h (default), 3d, 7d, 30d. Changing it re-filters everything. Keep the choice in the URL (`?w=7d`).
> 3. **Alerts strip:** today's price and volume alerts as small horizontal chips ("LT ▲ vol 2.7×", "KAYNES ▼ 5.1%"). Hidden when there are none.
> 4. **Needs attention:** priority-1 filings, newest first.
> 5. **Worth knowing:** priority-2 filings, more compact.
> 6. **Routine:** one collapsed row, "42 routine filings", that expands into a plain list.
>
> **Group filings into events.** Companies file several documents for one event (Home First filed results, a press release, a presentation and a CFO appointment within 10 minutes). Group filings from the same ticker within 3 hours of each other into one card. The card's priority is its highest filing's priority. Show the most important headline, plus a small "+3 more" that expands to the other filings in the group.
>
> **Each card shows:** ticker in bold and company name, category label, headline, time ("2h ago" if under 24h, else "27 Oct, 6:07 PM", IST), and a "PDF" link to the attachment. The whole card is tappable to expand.
>
> **Design:**
> - Calm and dense, like a well-made financial newspaper, not a dashboard. No gradients, no drop shadows, no emoji, no stock-photo vibes.
> - One accent colour used only for priority 1. Green and red only for price direction.
> - Numbers in a tabular/monospace figure style so they line up.
> - Supports light and dark mode from the system setting.
> - Good empty states: "Nothing needs your attention in the last 24h" is a feature, not an error.
>
> Data loads on the server (server components) and refreshes every 60 seconds (`revalidate = 60`).
>
> Run it locally, take screenshots at phone width (light and dark) with your browser tool, and show them to me. Then commit and push.

**You, after 2.3:** put it on the internet with Vercel. Five clicks:

1. vercel.com → **Add New… → Project** → pick the `finn` repo → **Import**.
2. **Root Directory:** click Edit → choose `web`.
3. **Environment Variables:** add `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (same values as your `.env`).
4. **Deploy.**
5. Open the link it gives you on your phone.

From now on, every push to GitHub updates the site automatically.

**Send Claude:** the 2.1 priority-1 list, and a screenshot of the site on your phone.
