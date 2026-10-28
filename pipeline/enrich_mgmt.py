"""Management change enrichment pipeline for FINN.

Workflow:
1. Select filings with category 'management_change', priority 1 or 2,
   no enrichment.people yet (unless forced), within the last 45 days.
2. Download PDF (cached locally), trim to first 6 pages, extract management
   changes using Gemini bulk model with pipeline/prompts/mgmt_v1.txt.
3. For newly appointed persons with is_top_role=True and no profile in the filing,
   search Serper ("<name>" "<company>" linkedin) cached in llm_cache (key=query)
   and synthesize a 2-sentence bio with Gemini bulk model and pipeline/prompts/bio_v1.txt.
4. Save the changes list to enrichment.people with bio and bio_source ("filing" or URL).
5. Rewrite the filing headline (summary) for top-role changes. Non-top-role changes
   keep their headline; if the filing has no top-role change, lower priority to 2.
"""

from typing import Any
from pathlib import Path
import os
import sys
import time
import io
import json
import logging
import hashlib
import datetime
import argparse
import requests
import pypdf
import zipfile

# Ensure Windows terminal supports UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import SEARCH_API_KEY
from pipeline.db import get_client, select, upsert
from pipeline.llm import call_json

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_mgmt")

# Suppress verbose httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

CACHE_PDF_DIR = PROJECT_ROOT / "pipeline" / "cache" / "pdfs"
CACHE_PDF_DIR.mkdir(parents=True, exist_ok=True)

PROMPT_MGMT_FILE = PROJECT_ROOT / "pipeline" / "prompts" / "mgmt_v1.txt"
PROMPT_BIO_FILE = PROJECT_ROOT / "pipeline" / "prompts" / "bio_v1.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SERPER_ENDPOINT = "https://google.serper.dev/search"


def load_prompt_templates() -> tuple[str, str]:
    """Load prompt templates for management change extraction and bio lookup."""
    if not PROMPT_MGMT_FILE.exists():
        raise FileNotFoundError(f"Management prompt file not found at {PROMPT_MGMT_FILE}")
    if not PROMPT_BIO_FILE.exists():
        raise FileNotFoundError(f"Bio prompt file not found at {PROMPT_BIO_FILE}")

    mgmt_prompt = PROMPT_MGMT_FILE.read_text(encoding="utf-8").strip()
    bio_prompt = PROMPT_BIO_FILE.read_text(encoding="utf-8").strip()
    return mgmt_prompt, bio_prompt


def download_pdf(url: str) -> bytes:
    """Download PDF with polite delay, browser User-Agent, exponential backoff, and local disk cache."""
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    file_name = url.split("/")[-1].split("?")[0]
    local_path = CACHE_PDF_DIR / f"{url_hash}_{file_name}"

    if local_path.exists():
        return local_path.read_bytes()

    headers = {"User-Agent": USER_AGENT}
    backoff_delays = [1, 2, 4]

    for attempt, delay in enumerate(backoff_delays, start=1):
        try:
            time.sleep(1)  # Polite delay to NSE / sources
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                content = response.content
                local_path.write_bytes(content)
                return content
            logger.warning("PDF download status %d for %s (attempt %d)", response.status_code, url, attempt)
        except Exception as exc:
            logger.warning("PDF download failed for %s (attempt %d): %s", url, attempt, exc)

        if attempt < len(backoff_delays):
            time.sleep(delay)

    raise RuntimeError(f"Failed to download PDF from {url} after {len(backoff_delays)} attempts")


def extract_pdf_from_bytes(data: bytes) -> bytes:
    """If bytes are a zip archive, extract the first PDF file found inside."""
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for fname in z.namelist():
                    if fname.lower().endswith(".pdf"):
                        return z.read(fname)
        except Exception as exc:
            logger.warning("Failed extracting PDF from zip file: %s", exc)
    return data


def trim_pdf_pages(pdf_bytes: bytes, max_pages: int = 6) -> bytes:
    """Trim PDF to at most max_pages (default 6) using pypdf."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    num_pages = len(reader.pages)
    if num_pages <= max_pages:
        return pdf_bytes

    writer = pypdf.PdfWriter()
    for i in range(min(max_pages, num_pages)):
        writer.add_page(reader.pages[i])

    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


def search_serper(query: str) -> dict[str, Any]:
    """Search Google via Serper API, caching results in llm_cache keyed on query.

    NOTE: This search is strictly for management bios only and is never used in research/.
    """
    if not SEARCH_API_KEY:
        logger.warning("SEARCH_API_KEY is not set. Skipping Serper lookup.")
        return {}

    # Check cache first
    try:
        cached_rows = select("llm_cache", key=query)
        if cached_rows and "output" in cached_rows[0]:
            logger.info("Serper cache hit for query: %s", query)
            return cached_rows[0]["output"]
    except Exception as exc:
        logger.warning("Error reading llm_cache for query '%s': %s", query, exc)

    headers = {
        "X-API-KEY": SEARCH_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": 5}

    for attempt in range(3):
        try:
            time.sleep(1)  # Polite delay
            resp = requests.post(SERPER_ENDPOINT, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    upsert(
                        "llm_cache",
                        {
                            "key": query,
                            "task": "serper",
                            "model": "serper",
                            "output": data,
                        },
                        on_conflict="key",
                    )
                except Exception as cache_exc:
                    logger.warning("Failed saving Serper result to llm_cache: %s", cache_exc)
                return data
            logger.warning("Serper status %d for '%s' (attempt %d)", resp.status_code, query, attempt + 1)
        except Exception as exc:
            logger.warning("Serper query failed for '%s' (attempt %d): %s", query, attempt + 1, exc)

        time.sleep(2 ** attempt)

    return {}


def synthesize_bio(
    name: str,
    role: str,
    company: str,
    bio_template: str,
) -> tuple[str | None, str | None]:
    """Look up person bio on LinkedIn via Serper and synthesize using Gemini bulk model."""
    query = f'"{name}" "{company}" linkedin'
    logger.info("Looking up LinkedIn bio for %s at %s (query: %s)", name, company, query)

    search_data = search_serper(query)
    organic = search_data.get("organic") or []

    if not organic:
        logger.info("No organic search results found for %s", query)
        return None, None

    # Format the prompt with top 3 organic results (use .replace to avoid KeyError on JSON braces)
    base_prompt = (
        bio_template.replace("{name}", name)
        .replace("{role}", role)
        .replace("{company}", company)
    )
    results_snippets = ["\nWeb search results:"]
    for i, item in enumerate(organic[:3], start=1):
        t = item.get("title", "")
        s = item.get("snippet", "")
        link = item.get("link", "")
        results_snippets.append(f"Result {i}:\nTitle: {t}\nSnippet: {s}\nLink: {link}")

    full_prompt = base_prompt + "\n" + "\n".join(results_snippets)

    try:
        res = call_json(task="bulk", prompt=full_prompt, prompt_version="v1")
        if isinstance(res, dict):
            bio = res.get("bio")
            source_url = res.get("source_url")
            if bio:
                return bio.strip(), source_url
    except Exception as exc:
        logger.error("Error synthesizing bio for %s: %s", name, exc)

    return None, None


def normalize_role(role: str) -> str:
    """Standardize role titles for concise, readable headlines."""
    if not role:
        return ""
    r = role.strip()
    r_lower = r.lower()

    if "chief financial officer" in r_lower or r_lower == "cfo":
        return "CFO"
    if (
        "managing director & chief executive officer" in r_lower
        or "managing director and chief executive officer" in r_lower
        or "md & ceo" in r_lower
        or "md and ceo" in r_lower
    ):
        return "MD & CEO"
    if "chief executive officer" in r_lower or r_lower == "ceo":
        return "CEO"
    if "managing director" in r_lower or r_lower == "md":
        return "MD"
    if "deputy managing director" in r_lower or "deputy md" in r_lower:
        return "Deputy MD"
    if "whole-time director" in r_lower or "whole time director" in r_lower or r_lower == "wtd":
        return "Whole-time Director"
    if "statutory auditor" in r_lower:
        return "Statutory Auditor"
    if "independent director" in r_lower:
        return "Independent Director"
    if "chairman" in r_lower:
        return "Chairman"

    return r


def format_effective_date(dt_str: str | None) -> str:
    """Format YYYY-MM-DD date into ' from DD Mon', e.g. ' from 27 Oct'."""
    if not dt_str:
        return ""
    try:
        dt = datetime.date.fromisoformat(dt_str)
        day = dt.day
        month = dt.strftime("%b")
        return f" from {day} {month}"
    except Exception:
        return ""


def generate_mgmt_headline(
    changes: list[dict[str, Any]],
    current_headline: str | None,
    current_subject: str,
) -> tuple[str, bool]:
    """Rewrite headline in Python for top-role changes.

    Returns:
        (headline, has_top_role)
    """
    top_changes = [c for c in changes if c.get("is_top_role")]

    if not top_changes:
        # Non-top-role changes keep their headline
        fallback = current_headline or current_subject or "Management Update"
        return fallback, False

    # Check for matching resignation & appointment pairs (e.g. CFO Rakesh Shah resigns; Arun Agrawal takes over)
    handled_indices: set[int] = set()
    pair_parts: list[str] = []

    resigned_indices = [i for i, c in enumerate(top_changes) if (c.get("change") or "").lower() == "resigned"]
    appointed_indices = [i for i, c in enumerate(top_changes) if (c.get("change") or "").lower() == "appointed"]

    for r_idx in resigned_indices:
        if r_idx in handled_indices:
            continue
        res = top_changes[r_idx]
        res_role = normalize_role(res.get("role", ""))
        for a_idx in appointed_indices:
            if a_idx in handled_indices:
                continue
            app = top_changes[a_idx]
            app_role = normalize_role(app.get("role", ""))
            if res_role.lower() == app_role.lower() and res_role:
                handled_indices.add(r_idx)
                handled_indices.add(a_idx)
                dt_suffix = format_effective_date(app.get("effective_date") or res.get("effective_date"))
                pair_parts.append(f"{res_role} {res.get('name')} resigns; {app.get('name')} takes over{dt_suffix}")
                break

    parts: list[str] = list(pair_parts)
    for i, c in enumerate(top_changes):
        if i in handled_indices:
            continue
        name = (c.get("name") or "").strip()
        role = normalize_role(c.get("role") or "")
        change = (c.get("change") or "").lower().strip()
        dt_suffix = format_effective_date(c.get("effective_date"))

        if change == "appointed":
            parts.append(f"{name} appointed {role}{dt_suffix}")
        elif change == "resigned":
            parts.append(f"{role} {name} resigns{dt_suffix}")
        elif change == "retired":
            parts.append(f"{role} {name} retires{dt_suffix}")
        elif change == "redesignated":
            parts.append(f"{name} redesignated {role}{dt_suffix}")
        elif change == "ceased":
            parts.append(f"{role} {name} ceases office{dt_suffix}")
        else:
            parts.append(f"{name} {change} as {role}{dt_suffix}")

    headline = "; ".join(parts) if parts else (current_headline or current_subject)
    return headline, True


def find_mgmt_filings(lookback_days: int = 45, force: bool = False) -> list[dict[str, Any]]:
    """Query filings table for management_change filings within lookback_days."""
    client = get_client()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff_utc = (now_utc - datetime.timedelta(days=lookback_days)).isoformat()

    logger.info("Querying management_change filings since %s...", cutoff_utc)
    res = (
        client.table("filings")
        .select("*")
        .eq("category", "management_change")
        .in_("priority", [1, 2])
        .gte("filed_at", cutoff_utc)
        .order("filed_at", desc=True)
        .execute()
    )

    rows = res.data or []
    if not force:
        pending = [r for r in rows if not (r.get("enrichment") or {}).get("people")]
    else:
        pending = rows

    logger.info("Found %d total management_change filings (%d pending enrichment).", len(rows), len(pending))
    return pending


def get_company_names() -> dict[str, str]:
    """Retrieve mapping of ticker -> company name."""
    companies = select("companies")
    return {c["ticker"]: c["name"] for c in companies if "ticker" in c and "name" in c}


def enrich_mgmt_filing(
    filing: dict[str, Any],
    mgmt_prompt: str,
    bio_prompt: str,
    company_names: dict[str, str],
) -> dict[str, Any] | None:
    """Enrich a single management_change filing with extracted people, bios, and headline."""
    ticker = filing["ticker"]
    filing_id = filing["id"]
    attachment_url = filing.get("attachment_url")
    company_name = company_names.get(ticker, ticker)

    if not attachment_url:
        logger.warning("[%s] Filing %s has no attachment_url. Skipping.", ticker, filing_id)
        return None

    logger.info("[%s] Processing management filing %s (%s)", ticker, filing_id, filing.get("subject"))

    # 1. Download and trim PDF (first 6 pages, unpacking zip if needed)
    raw_bytes = download_pdf(attachment_url)
    pdf_bytes = extract_pdf_from_bytes(raw_bytes)
    trimmed_bytes = trim_pdf_pages(pdf_bytes, max_pages=6)

    # 2. Extract changes using Gemini bulk model
    extracted = call_json(
        task="bulk",
        prompt=mgmt_prompt,
        prompt_version="v1",
        pdf_bytes=trimmed_bytes,
    )

    if isinstance(extracted, list):
        if len(extracted) > 0 and isinstance(extracted[0], dict):
            if "changes" in extracted[0]:
                extracted = extracted[0]
            else:
                extracted = {"changes": extracted}
        else:
            extracted = {"changes": []}

    if not isinstance(extracted, dict) or "changes" not in extracted:
        logger.warning("[%s] Invalid extraction output for filing %s: %s", ticker, filing_id, extracted)
        return None

    changes: list[dict[str, Any]] = extracted.get("changes") or []
    logger.info("[%s] Extracted %d person change(s) from filing %s", ticker, len(changes), filing_id)

    # 3. For each person, attach bio and bio_source
    enriched_people: list[dict[str, Any]] = []
    for p in changes:
        p_name = (p.get("name") or "").strip()
        p_role = (p.get("role") or "").strip()
        p_change = (p.get("change") or "").lower().strip()
        p_profile = p.get("profile")
        p_is_top = bool(p.get("is_top_role"))

        bio: str | None = None
        bio_source: str | None = None

        if p_profile:
            bio = p_profile.strip()
            bio_source = "filing"
        elif p_change == "appointed" and p_is_top and not p_profile:
            # Need web lookup
            searched_bio, search_source = synthesize_bio(
                name=p_name,
                role=p_role,
                company=company_name,
                bio_template=bio_prompt,
            )
            bio = searched_bio
            bio_source = search_source

        person_data = {
            **p,
            "bio": bio,
            "bio_source": bio_source,
        }
        enriched_people.append(person_data)

    # 4. Rewrite headline and handle priority
    current_summary = filing.get("summary")
    current_subject = filing.get("subject", "")
    new_headline, has_top_role = generate_mgmt_headline(enriched_people, current_summary, current_subject)

    # 5. Save to database
    client = get_client()
    enr = filing.get("enrichment") or {}
    enr["people"] = enriched_people

    update_payload: dict[str, Any] = {
        "enrichment": enr,
        "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    if has_top_role:
        update_payload["summary"] = new_headline
    else:
        # Non-top-role changes keep their headline; if the filing has no top-role change, lower priority to 2
        if filing.get("priority") == 1:
            logger.info("[%s] No top-role change found for filing %s; lowering priority 1 -> 2.", ticker, filing_id)
            update_payload["priority"] = 2

    client.table("filings").update(update_payload).eq("id", filing_id).execute()

    return {
        "ticker": ticker,
        "id": filing_id,
        "filed_at": filing.get("filed_at"),
        "old_headline": current_summary or current_subject,
        "new_headline": update_payload.get("summary", current_summary or current_subject),
        "priority": update_payload.get("priority", filing.get("priority")),
        "people": enriched_people,
    }


def run_pipeline(lookback_days: int = 45, force: bool = False) -> list[dict[str, Any]]:
    """Execute management change enrichment pipeline."""
    mgmt_prompt, bio_prompt = load_prompt_templates()
    company_names = get_company_names()
    pending = find_mgmt_filings(lookback_days=lookback_days, force=force)

    results: list[dict[str, Any]] = []
    for f in pending:
        try:
            res = enrich_mgmt_filing(f, mgmt_prompt, bio_prompt, company_names)
            if res:
                results.append(res)
        except Exception as exc:
            logger.error("Failed processing management change for %s (%s): %s", f.get("ticker"), f.get("id"), exc)

    return results


def print_summary(records: list[dict[str, Any]]) -> None:
    """Print clean summary showing each management filing."""
    print("\n" + "=" * 90)
    print("FINN MANAGEMENT CHANGE ENRICHMENT SUMMARY")
    print("=" * 90)

    if not records:
        print("No management change filings were processed in this run.")
        print("=" * 90 + "\n")
        return

    for idx, r in enumerate(records, start=1):
        ticker = r["ticker"]
        new_headline = r["new_headline"]
        people = r.get("people") or []
        priority = r.get("priority")

        print(f"\n[{idx}] {ticker} (Priority {priority})")
        print(f"    Headline: {new_headline}")
        print("    People changes:")
        if not people:
            print("      (No individuals extracted)")
        for p in people:
            name = p.get("name", "Unknown")
            role = p.get("role", "Unknown")
            change = p.get("change", "Unknown")
            is_top = " [Top Role]" if p.get("is_top_role") else ""
            bio = p.get("bio")
            source = p.get("bio_source") or "None"

            print(f"      • {name} — {role} ({change}){is_top}")
            if bio:
                print(f"        Bio ({source}): {bio}")
            else:
                print(f"        Bio: None (source: {source})")

    print("\n" + "-" * 90)
    print(f"Total management filings enriched: {len(records)}")
    print("=" * 90 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich management change filings for FINN")
    parser.add_argument("--days", type=int, default=45, help="Lookback window in days (default: 45)")
    parser.add_argument("--force", action="store_true", help="Re-process filings even if already enriched")
    args = parser.parse_args()

    records = run_pipeline(lookback_days=args.days, force=args.force)
    print_summary(records)


if __name__ == "__main__":
    main()
