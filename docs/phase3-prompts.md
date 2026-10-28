# Phase 3 · Enrichment — Antigravity prompts

Three prompts, **one new Antigravity conversation each**. Paste, approve the plan, send Claude the final message.

At the end, results cards show real numbers and management cards say who the person is.

---

## 3.1 · Results card: Revenue, EBITDA, PBT, PAT

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> Build `pipeline/enrich_results.py`. The design rule: **the LLM only copies numbers from the PDF; Python does all the maths.**
>
> **1. Let `llm.py` accept a PDF.** Add an optional `pdf_bytes` argument to `call_json`, sent to Gemini as a PDF part (`application/pdf`). Include the sha256 of the PDF bytes in the cache key.
>
> **2. Pick the right PDF.** For each results event (same ticker, category `results`, within 3 hours, last 45 days) that has no `enrichment.results` yet, try its filings' PDFs one by one, starting with subjects like "Outcome of Board Meeting" / "Financial Result Updates". Download each PDF (cache the file locally, gitignored), keep only the first 15 pages (pypdf), and send them with the prompt below (task `"reasoning"`). Stop at the first PDF where `found` is true.
>
> **3. Save the prompt below as `pipeline/prompts/results_v1.txt`:**
>
> ```
> You extract numbers from an Indian listed company's quarterly financial results filing. Copy numbers exactly as printed. Do not calculate anything.
>
> The results statement usually has columns for the quarter just ended, the previous quarter, and the same quarter last year, plus half-year or year columns that you ignore. If both consolidated and standalone statements exist, use consolidated.
>
> Return JSON:
> {
>   "found": true or false (false if this document has no results statement),
>   "basis": "consolidated" or "standalone",
>   "unit": the unit printed on the statement, exactly as written (e.g. "₹ in crore", "Rs. in lakhs", "₹ million"),
>   "is_lender": true if it is a bank, NBFC or housing-finance format (interest income, impairment or provisions),
>   "periods": {"current": "...", "previous_quarter": "...", "year_ago": "..."} as printed,
>   "lines": {
>     "revenue_from_operations": {"current": n, "previous_quarter": n, "year_ago": n},
>     "other_income": {...},
>     "finance_costs": {...},
>     "depreciation": {...},
>     "exceptional_items": {...},
>     "profit_before_tax": {...},
>     "tax_expense": {...},
>     "profit_after_tax": {...}
>   },
>   "page": the PDF page number where the statement is,
>   "notes": anything unusual, at most 20 words, or null
> }
>
> profit_after_tax is the net profit for the period (for consolidated, the total before the split between owners and non-controlling interests).
> For lenders, revenue_from_operations is the top line ("Revenue from operations", or "Interest earned" / "Total income" if that is the first line).
> Numbers in brackets are negative. Use null for any line that is not printed. Never guess.
> ```
>
> **4. Compute in Python:**
> - Convert everything to **₹ crore** from the printed unit (lakh ÷ 100, million ÷ 10, thousand ÷ 10,000, rupees ÷ 1,00,00,000). Fail loudly on a unit you don't recognise.
> - **EBITDA** = profit_before_tax − exceptional_items + finance_costs + depreciation − other_income. For lenders, EBITDA is null.
> - QoQ % and YoY % for Revenue, EBITDA, PBT, PAT; EBITDA margin and its change in percentage points.
> - **Sanity check:** PBT − tax should equal PAT within 2%. If so, set `"verified": true`, else `false`.
> - Save to the results filing's `enrichment.results` (keep the existing `why`): basis, unit "₹ cr", periods, the four metrics with current / QoQ / YoY, margin, is_lender, verified, page, source PDF url.
> - Replace the event's headline (`summary` of the main results filing) with one built in Python from the numbers, e.g. "Revenue +12% YoY, PAT −35% YoY". Lenders: "Revenue +18% YoY, PAT +27% YoY".
>
> **5. Test against known figures.** Reported Q2 FY27 numbers (consolidated unless noted; small differences can be standalone vs consolidated):
> - CIPLA: PAT ≈ ₹878 cr, down about 35% YoY
> - NETWEB: revenue ≈ ₹1,323 cr; PAT ≈ ₹137 cr
> - HOMEFIRST: PAT ≈ ₹170 cr (it's a lender)
> - NAZARA: revenue ≈ ₹803 cr, EBITDA ≈ ₹120 cr (company-reported EBITDA can differ slightly from our formula)
>
> **6.** Add a `python -m pipeline.enrich_results` step after classify in `filings.yml`.
>
> Run it. Show a table of every company processed: basis, revenue, EBITDA, PBT, PAT (₹ cr), QoQ and YoY for revenue and PAT, check flag, and how the four test companies compare with the known figures. Commit and push.

**Send Claude:** that table.

---

## 3.2 · Management change: who is this person?

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> Build `pipeline/enrich_mgmt.py` for filings with category `management_change`, priority 1 or 2, no `enrichment.people` yet, last 45 days.
>
> **1. Read the filing.** Send the PDF (first 6 pages) with the prompt below, task `"bulk"`. Save it as `pipeline/prompts/mgmt_v1.txt`:
>
> ```
> You read an Indian listed company's stock-exchange disclosure about a change in its senior management or board. List every person whose position changes.
>
> Return JSON:
> {"changes": [{
>   "name": "...",
>   "role": "the role as stated, e.g. Chief Financial Officer",
>   "change": "appointed" | "resigned" | "retired" | "redesignated" | "ceased",
>   "effective_date": "YYYY-MM-DD" or null,
>   "reason": "the stated reason, at most 15 words" or null,
>   "profile": "the brief profile given in the filing, summarised in at most 40 words" or null,
>   "is_top_role": true if CEO, MD, CFO, chairman, whole-time director or statutory auditor
> }]}
>
> Use only this document. Do not add facts from outside knowledge. If the document gives no profile for a person, profile is null.
> ```
>
> **2. Look people up only when needed.** For each *appointed* person with `is_top_role` true and no profile, search with Serper (`SEARCH_API_KEY`, endpoint `https://google.serper.dev/search`) for `"<name>" "<company>" linkedin`. Pass the top 3 results' titles, snippets and links to Gemini (task `"bulk"`) with this prompt, saved as `pipeline/prompts/bio_v1.txt`:
>
> ```
> Below are web search results about {name}, newly appointed as {role} at {company}. Write their professional background in at most 2 sentences: previous employers and roles, and education if shown. Use only facts from results that clearly refer to this person: same name and a link to {company} or to the role. If no result clearly matches, return {"bio": null, "source_url": null}. Otherwise return {"bio": "...", "source_url": "<the link you used>"}.
> ```
>
> Cache search results in `llm_cache` (key = query) so each person is searched only once. **This search is for management bios only and must never be imported from `research/`.**
>
> **3. Save** to `enrichment.people`: the list of changes, each with `bio` and `bio_source` ("filing" or the URL).
>
> **4. Rewrite the headline in Python** for top-role changes, e.g. "Rinkoo Somani appointed CFO from 27 Oct" or "CFO Rakesh Shah resigns; Arun Agrawal takes over". This replaces vague headlines like "Change in Management". Non-top-role changes keep their headline; if the filing has no top-role change, lower the priority to 2.
>
> **5.** Add `python -m pipeline.enrich_mgmt` after `enrich_results` in `filings.yml`.
>
> Run it. Show each management filing: ticker, new headline, people (name, role, change), bio and bio source. Commit and push.

**Send Claude:** that list. I'll check that the bios match the right people.

---

## 3.3 · Show it on the cards

> Read `.agent/rules/finn.md` first. Plan before coding.
>
> Update the Brief screen in `web/` to use the new enrichment.
>
> **1. Results block**, inside any card whose event has `enrichment.results`:
> - A compact 4-row table: Revenue, EBITDA, PBT, PAT. Columns: this quarter (₹ cr), QoQ %, YoY %.
> - Monospace, right-aligned numbers. Green or red **only** on the % changes.
> - One line under it: "EBITDA margin 18.2% · +0.6 pt YoY".
> - A small footer: "Consolidated · from results PDF p.3" linking to the PDF. If `verified` is false, add "· figures need a check".
> - Lenders: show "—" for EBITDA and margin, with the footer note "EBITDA not meaningful for lenders".
>
> **2. People block**, inside any card with `enrichment.people`: each top-role person as name (bold), role, change and effective date, then their bio in smaller text with its source ("from the filing" or the site's domain as a link).
>
> **3. Events with more than one kind of news.** Show a chip for every distinct category in the group (max 3, e.g. `M&A` `RESULTS`). If the group has a results block and the main headline is about something else, show the results block too, with a small "Also: Q2 results" label above it.
>
> **4. Remove noise.** Hide the "Details" box when the description is NSE boilerplate (contains "has informed the Exchange").
>
> **5. Alert chips:** show the day's price change next to volume, e.g. "HINDUNILVR vol 2.1× · −1.4%". The arrow and colour follow the price change.
>
> Keep the existing design language. Run locally, take phone-width screenshots of the TVS, Home First and Nazara cards (use the 30d window), show me, then commit and push. Vercel updates automatically.

**You:** open the site on your phone, switch to **30d**, and send Claude a screenshot of the Home First card opened.
