# Phase 6 · Ship — checklist

Four steps. Do them in this order.

---

## 1 · Antigravity: final cleanup (one prompt, new conversation)

> Read `.agent/rules/finn.md` first. This is the final pass before submission: **fix only what's broken, add no features.**
>
> 1. **Secrets audit.** Search the whole repo and the full git history (`git log -p --all`) for anything that looks like a key: `sb_secret_`, `sb_publishable_`, `AIza`, `AQ.`, `ghp_`, `github_pat_`, long hex strings, and the Serper key pattern. Report every hit with file and commit. Confirm `.env` and `web/.env.local` were never committed. If a real secret appears in history, tell me. Don't rewrite history without asking.
> 2. **Remove clutter:** scratch and test scripts (e.g. `capture_*.py`, `test_*.py`, `rerun_*.py`, `inspect_*.py`, `print_*.py`, `check_*.py`, `show_*.py`), stray PNGs outside `docs/screenshots/`, the `notes` file, and any cache folders. Make sure `pipeline/cache/` is gitignored. Keep `docs/screenshots/`.
> 3. **`.env.example`** lists every variable with empty values: `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SEARCH_API_KEY`, `GH_DISPATCH_TOKEN`.
> 4. **README.md** (concise, at most ~150 lines):
>    - One paragraph on what FINN is, plus the live link https://finn-lovat-two.vercel.app
>    - Three screenshots from `docs/screenshots/` (Brief, a company page, research progress).
>    - An architecture diagram as a Mermaid block: GitHub Actions jobs → Supabase → Vercel app, with NSE / Yahoo / screener.in as sources and Gemini via `llm.py`.
>    - **Model routing and cost:** which model does which task, caching by content hash, the rule pre-filter, PDF-only-when-needed, ₹0 total.
>    - **How promised-vs-delivered works:** extract (cheap model) → verify quotes against pages (Python) → group targets and compute revisions (Python) → judge (strong model) → rule overrides (Python). List the override rules.
>    - **Repo map:** one line per folder and key file.
>    - **Run it yourself:** clone, `.env` from `.env.example`, run `supabase/migrations/*.sql`, `pip install -r requirements.txt`, `python -m pipeline.seed`, `python -m research.run --ticker DIXON`, and `cd web && npm i && npm run dev`.
>    - Known limits (copy from the writeup I'll give you, or keep it to 5 bullets).
> 5. **Smoke test:** `npm run build` in `web/` with zero errors. Then on the live site check each of these returns 200 and renders: `/`, `/?w=7d`, `/research`, `/settings`, `/c/DIXON`, `/c/HOMEFIRST`, `/c/BAJFINANCE`, `/c/ZZZZ` (the unknown-ticker state). Trigger the filings workflow once from GitHub and confirm it passes.
> 6. **`docs/ai-history/`:** list what's there, and tell me which conversations are missing (by phase).
>
> Commit (`chore: final cleanup, README`) and push. Report the audit results first.

---

## 2 · You: replace the three keys that appeared in screenshots

The Supabase secret key, the Gemini key and the Serper key were visible in screenshots in the Claude chat, which goes to ENAM as your build history. Replace them so the copies in the chat are dead.

| Key | Create the new one | Then put it in |
| --- | --- | --- |
| Supabase secret | Supabase → Project Settings → API Keys → create a new secret key → delete the old one | `.env` (`SUPABASE_SECRET_KEY`) and GitHub Secrets |
| Gemini | aistudio.google.com → API keys → Create key → delete the old one | `.env` (`GEMINI_API_KEY`) and GitHub Secrets |
| Serper | serper.dev dashboard → API key → regenerate | `.env` (`SEARCH_API_KEY`) and GitHub Secrets |

GitHub Secrets: repo → Settings → Secrets and variables → Actions → pencil icon on each → paste → Update.

**Check:** GitHub → Actions → **Fetch Exchange Filings** → Run workflow. A green tick means the new keys work.

The publishable key and the GitHub token don't need changing.

---

## 3 · You: build history

1. **Antigravity:** export any conversation missing from `docs/ai-history/` (Antigravity tells you which in step 1). Name them by phase, e.g. `05-company-page.md`. If the export button does nothing, copy the chat into a `.md` file by hand. Commit and push.
2. **Claude:** in this chat, click **Share** (top right) → create a link → copy it. Paste it into the submission email doc where it says [ADD CLAUDE SHARE LINK].

---

## 4 · You: final check and send

- [ ] Open https://finn-lovat-two.vercel.app on your **real phone**, in a private tab. Tap through the Brief, one company page and Research. Share → Add to Home Screen, then open it from the icon.
- [ ] Edit the submission email doc into your own voice. Fill in your name and contact details and the Claude share link.
- [ ] Send to **assessment@enam.com** with the subject exactly **ENAM - IIT screening - 2027**.
- [ ] Don't push changes to `main` after sending, unless something is broken.
