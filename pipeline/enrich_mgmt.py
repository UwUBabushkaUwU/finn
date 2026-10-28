"""Management change enrichment pipeline for FINN.

Workflow:
1. Select filings with category 'management_change', priority 1 or 2,
   no enrichment.people yet (unless forced), within the last 45 days.
2. Download PDF (cached locally, unpacking ZIP archives if needed), trim to
   first 6 pages, extract management changes with Gemini bulk model and
   pipeline/prompts/mgmt_v1.txt.
3. Merge people with the same name in one filing into one entry
   (e.g. "N. Venkataraman moves from CFO to Deputy MD").
4. For newly appointed persons with is_top_role=True and no profile in the filing:
   - Strict search: "<name>" "<company>" linkedin
   - If strict returns no match, fallback search: "<name>" <role short form, e.g. CFO> linkedin (no company).
   - Searches cached in llm_cache (key=query).
   - Synthesize bio using Gemini bulk model with pipeline/prompts/bio_v2.txt.
5. Rewrite headline for EVERY filing with people:
   - At most 2 changes, ordered CEO/MD > CFO > chairman > whole-time director;
     appointments and resignations before redesignations.
   - Strip Mr./Ms./Shri.
   - Add "+N more" if there are other changes.
6. Priority:
   - Any top-role appointment or resignation (including CFO-designate) is priority 1.
   - Redesignations only are priority 2.
   - Other management changes without top roles are priority 2.
7. Duplicates:
   - If a filing's people list matches another filing for the same ticker within 7 days,
     keep the earliest and set the others to priority 3 with headline "Duplicate of earlier filing".
"""

from typing import Any
from pathlib import Path
import os
import sys
import time
import io
import re
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
PROMPT_BIO_FILE = PROJECT_ROOT / "pipeline" / "prompts" / "bio_v3.txt"

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


def clean_person_name(name: str) -> str:
    """Strip honorifics (Mr., Ms., Mrs., Shri, Smt., Dr.) from a person's name."""
    if not name:
        return ""
    cleaned = re.sub(r"^(Mr\.|Ms\.|Mrs\.|Shri\.?|Smt\.?|Dr\.)\s+", "", name.strip(), flags=re.IGNORECASE)
    return cleaned.strip()


def normalize_role(role: str) -> str:
    """Standardize role titles for concise, readable headlines."""
    if not role:
        return ""
    r = role.strip()
    r_lower = r.lower()

    if "chief financial officer" in r_lower or r_lower == "cfo":
        if "designate" in r_lower:
            return "CFO Designate"
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
    if "general counsel" in r_lower or "group head - legal" in r_lower:
        return "General Counsel"
    if "chief compliance officer" in r_lower or "compliance officer" in r_lower:
        return "Chief Compliance Officer"

    return r


def get_role_short_form(role: str) -> str:
    """Extract standard short form for web search (e.g. CFO, CEO, MD, etc.)."""
    r_lower = role.lower()
    if "cfo" in r_lower or "financial" in r_lower:
        return "CFO"
    if "ceo" in r_lower or "chief executive" in r_lower:
        return "CEO"
    if "managing director" in r_lower or "md" in r_lower:
        return "MD"
    if "chairman" in r_lower:
        return "Chairman"
    if "whole-time director" in r_lower or "whole time director" in r_lower:
        return "Whole-time Director"
    if "director" in r_lower:
        return "Director"
    if "auditor" in r_lower:
        return "Auditor"
    if "counsel" in r_lower or "legal" in r_lower:
        return "General Counsel"
    if "compliance" in r_lower or "cco" in r_lower:
        return "Chief Compliance Officer"
    if "technology" in r_lower or "cto" in r_lower:
        return "CTO"
    if "operations" in r_lower or "coo" in r_lower:
        return "COO"
    return normalize_role(role)


def is_top_role_person(p: dict[str, Any]) -> bool:
    """Check if person change is a top-level role (including CFO-designate)."""
    if p.get("is_top_role"):
        return True
    role = (p.get("role") or "").lower()
    return any(
        k in role
        for k in (
            "cfo",
            "ceo",
            "md",
            "managing director",
            "chairman",
            "whole-time director",
            "whole time director",
            "statutory auditor",
        )
    )


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
            time.sleep(1)  # Polite delay
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                content = response.content
                local_path.write_bytes(content)
                return content
            logger.warning("Download status %d for %s (attempt %d)", response.status_code, url, attempt)
        except Exception as exc:
            logger.warning("Download failed for %s (attempt %d): %s", url, attempt, exc)

        if attempt < len(backoff_delays):
            time.sleep(delay)

    raise RuntimeError(f"Failed to download attachment from {url} after {len(backoff_delays)} attempts")


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


def _lookup_bio_query(
    name: str,
    role: str,
    company: str,
    query: str,
    bio_template: str,
) -> tuple[str | None, str | None]:
    """Run search query through Serper and prompt Gemini v2 to synthesize a bio."""
    logger.info("Searching Serper with query: %s", query)
    search_data = search_serper(query)
    organic = search_data.get("organic") or []

    if not organic:
        logger.info("No organic search results found for query: %s", query)
        return None, None

    # Format prompt using replace to avoid KeyError on JSON braces
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
        res = call_json(task="bulk", prompt=full_prompt, prompt_version="v3")
        if isinstance(res, dict):
            bio = res.get("bio")
            source_url = res.get("source_url")
            if bio:
                return bio.strip(), source_url
    except Exception as exc:
        logger.error("Error synthesizing bio for query '%s': %s", query, exc)

    return None, None


def synthesize_bio(
    name: str,
    role: str,
    company: str,
    bio_template: str,
) -> tuple[str | None, str | None]:
    """Look up person bio via strict search, and fallback to role-short-form search if no match."""
    clean_name = clean_person_name(name)
    role_short = get_role_short_form(role)

    # 1. Strict search: "<name>" "<company>" linkedin
    strict_query = f'"{clean_name}" "{company}" linkedin'
    bio, src = _lookup_bio_query(clean_name, role, company, strict_query, bio_template)
    if bio:
        return bio, src

    # 2. Fallback search: "<name>" <role short form, e.g. CFO> linkedin (no company)
    fallback_query = f'"{clean_name}" {role_short} linkedin'
    logger.info("Strict search returned no match for %s. Trying fallback query: %s", clean_name, fallback_query)
    return _lookup_bio_query(clean_name, role, company, fallback_query, bio_template)


def merge_people_entries(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge people with the same name in one filing into one entry.

    e.g. 'N. Venkataraman moves from CFO to Deputy MD'
    """
    if not people:
        return []

    grouped: dict[str, list[dict[str, Any]]] = {}
    for p in people:
        raw_name = p.get("name") or ""
        norm_name = clean_person_name(raw_name).lower()
        if not norm_name:
            continue
        grouped.setdefault(norm_name, []).append(p)

    merged: list[dict[str, Any]] = []
    for norm_name, entries in grouped.items():
        clean_name = clean_person_name(entries[0].get("name", ""))
        if len(entries) == 1:
            entry = dict(entries[0])
            entry["name"] = clean_name
            merged.append(entry)
            continue

        # Multiple entries for same person
        # Check for moves / redesignations:
        # e.g., one ceased/resigned from Role A, and one appointed/redesignated to Role B
        left_entries = [
            e for e in entries if (e.get("change") or "").lower() in ("ceased", "resigned", "stepped down")
        ]
        joined_entries = [
            e for e in entries if (e.get("change") or "").lower() in ("appointed", "redesignated", "joined")
        ]

        if left_entries and joined_entries:
            role_from = normalize_role(left_entries[0].get("role", ""))
            role_to = normalize_role(joined_entries[0].get("role", ""))
            combined_role = f"moves from {role_from} to {role_to}"
            combined_change = "moves"
            is_top = any(is_top_role_person(e) for e in entries)
        else:
            # Pick primary entry (highest role rank)
            sorted_entries = sorted(
                entries,
                key=lambda e: (
                    get_role_rank(normalize_role(e.get("role", ""))),
                    get_action_rank(e.get("change", "")),
                ),
            )
            primary = sorted_entries[0]
            combined_role = primary.get("role", "")
            combined_change = primary.get("change", "")
            is_top = any(is_top_role_person(e) for e in entries)

        eff_date = next((e.get("effective_date") for e in entries if e.get("effective_date")), None)
        reason = next((e.get("reason") for e in entries if e.get("reason")), None)
        profile = next((e.get("profile") for e in entries if e.get("profile")), None)
        bio = next((e.get("bio") for e in entries if e.get("bio")), None)
        bio_src = next((e.get("bio_source") for e in entries if e.get("bio_source")), None)

        merged.append({
            "name": clean_name,
            "role": combined_role,
            "change": combined_change,
            "effective_date": eff_date,
            "reason": reason,
            "profile": profile,
            "is_top_role": is_top,
            "bio": bio,
            "bio_source": bio_src,
        })

    return merged


def get_role_rank(role: str) -> int:
    """Rank roles: CEO/MD (1) > CFO (2) > Chairman (3) > Whole-time Director (4) > Other (5)."""
    r = role.lower()
    if "ceo" in r or "managing director" in r or "md" in r:
        return 1
    if "cfo" in r or "financial" in r:
        return 2
    if "chairman" in r:
        return 3
    if "whole-time director" in r or "whole time director" in r or "director" in r:
        return 4
    if "counsel" in r or "legal" in r or "compliance" in r or "auditor" in r:
        return 5
    return 6


def get_action_rank(change: str) -> int:
    """Rank actions: appointments and resignations (1) before redesignations (2)."""
    c = change.lower()
    if c in ("appointed", "resigned", "retired", "ceased"):
        return 1
    if c in ("redesignated", "moves"):
        return 2
    return 3


def generate_mgmt_headline(
    people: list[dict[str, Any]],
    current_headline: str | None,
    current_subject: str,
) -> str:
    """Rewrite headline for every filing with people.

    Rules:
    - At most 2 changes, ordered CEO/MD > CFO > chairman > whole-time director;
      appointments and resignations before redesignations.
    - Strip Mr./Ms./Shri.
    - Add '+N more' if there are other changes.
    """
    if not people:
        return current_headline or current_subject or "Management Update"

    # Sort people according to precedence
    sorted_people = sorted(
        people,
        key=lambda p: (
            get_role_rank(normalize_role(p.get("role", ""))),
            get_action_rank(p.get("change", "")),
        ),
    )

    selected = sorted_people[:2]
    remaining_count = len(sorted_people) - len(selected)

    # Check if the 2 selected changes are a resignation and appointment for the same role
    # e.g. "General Counsel Sudhir Kumar Jha retires; Jigar Shah appointed"
    # or "CFO Rakesh Shah resigns; Arun Agrawal takes over"
    parts: list[str] = []
    if len(selected) == 2:
        p0, p1 = selected[0], selected[1]
        r0 = normalize_role(p0.get("role", ""))
        r1 = normalize_role(p1.get("role", ""))
        c0 = (p0.get("change") or "").lower()
        c1 = (p1.get("change") or "").lower()

        if r0.lower() == r1.lower() and r0:
            dt0 = format_effective_date(p0.get("effective_date"))
            dt1 = format_effective_date(p1.get("effective_date"))
            if c0 in ("resigned", "retired", "ceased") and c1 == "appointed":
                verb0 = "retires" if c0 == "retired" else ("resigns" if c0 == "resigned" else "ceases office")
                parts = [f"{r0} {p0['name']} {verb0}{dt0}", f"{p1['name']} appointed{dt1}"]
            elif c1 in ("resigned", "retired", "ceased") and c0 == "appointed":
                verb1 = "retires" if c1 == "retired" else ("resigns" if c1 == "resigned" else "ceases office")
                parts = [f"{r1} {p1['name']} {verb1}{dt1}", f"{p0['name']} appointed{dt0}"]

    if not parts:
        for p in selected:
            name = clean_person_name(p.get("name", ""))
            role = normalize_role(p.get("role", ""))
            change = (p.get("change") or "").lower().strip()
            dt_suffix = format_effective_date(p.get("effective_date"))

            if change == "moves" or "moves from" in role:
                parts.append(f"{name} {role}{dt_suffix}")
            elif change == "appointed":
                parts.append(f"{name} appointed {role}{dt_suffix}")
            elif change == "resigned":
                parts.append(f"{role} {name} resigns{dt_suffix}")
            elif change == "retired":
                parts.append(f"{role} {name} retires{dt_suffix}")
            elif change == "ceased":
                parts.append(f"{role} {name} ceases office{dt_suffix}")
            elif change == "redesignated":
                parts.append(f"{name} redesignated {role}{dt_suffix}")
            else:
                parts.append(f"{name} {change} as {role}{dt_suffix}")

    headline = "; ".join(parts)
    if remaining_count > 0:
        headline += f"; +{remaining_count} more"

    return headline


def determine_priority(people: list[dict[str, Any]]) -> int:
    """Determine filing priority based on top-role changes.

    - Any top-role appointment or resignation (including CFO-designate) is priority 1.
    - Redesignations only are priority 2.
    - Other changes are priority 2.
    """
    if not people:
        return 2

    has_appoint_or_resign = any(
        is_top_role_person(p) and (p.get("change") or "").lower() in ("appointed", "resigned", "retired", "ceased")
        for p in people
    )
    if has_appoint_or_resign:
        return 1

    has_top_role = any(is_top_role_person(p) for p in people)
    if has_top_role:
        return 2

    return 2


def deduplicate_filings(filings: list[dict[str, Any]]) -> None:
    """Check for duplicate filings for the same ticker within 7 days.

    Keep the earliest and set the others to priority 3 with headline 'Duplicate of earlier filing'.
    """
    client = get_client()
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for f in filings:
        t = f.get("ticker")
        if t:
            by_ticker.setdefault(t, []).append(f)

    for ticker, group in by_ticker.items():
        if len(group) < 2:
            continue

        # Sort earliest first
        sorted_group = sorted(group, key=lambda x: x.get("filed_at") or "")

        for i in range(len(sorted_group)):
            earlier = sorted_group[i]
            earlier_people = earlier.get("people") or []
            if not earlier_people:
                continue
            earlier_names = {clean_person_name(p.get("name", "")).lower() for p in earlier_people}

            for j in range(i + 1, len(sorted_group)):
                later = sorted_group[j]
                later_people = later.get("people") or []
                if not later_people:
                    continue
                later_names = {clean_person_name(p.get("name", "")).lower() for p in later_people}

                if earlier_names == later_names:
                    # Check date diff <= 7 days
                    dt_earlier = datetime.datetime.fromisoformat(earlier["filed_at"])
                    dt_later = datetime.datetime.fromisoformat(later["filed_at"])
                    diff_days = abs((dt_later - dt_earlier).total_seconds()) / 86400.0

                    if diff_days <= 7.0:
                        logger.info(
                            "[%s] Filing %s is a duplicate of earlier filing %s (diff: %.1f days). Setting priority 3.",
                            ticker,
                            later["id"],
                            earlier["id"],
                            diff_days,
                        )
                        later["priority"] = 3
                        later["new_headline"] = "Duplicate of earlier filing"

                        # Persist to Supabase
                        client.table("filings").update({
                            "priority": 3,
                            "summary": "Duplicate of earlier filing",
                        }).eq("id", later["id"]).execute()


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

    logger.info("Found %d total management_change filings (%d to process).", len(rows), len(pending))
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
    raw_people: list[dict[str, Any]] = []
    for p in changes:
        p_name = clean_person_name(p.get("name") or "")
        p_role = (p.get("role") or "").strip()
        p_change = (p.get("change") or "").lower().strip()
        p_profile = p.get("profile")
        p_is_top = is_top_role_person(p)

        bio: str | None = None
        bio_source: str | None = None

        if p_profile:
            bio = p_profile.strip()
            bio_source = "filing"
        elif p_change == "appointed" and p_is_top and not p_profile:
            # Need web lookup (strict + fallback)
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
            "name": p_name,
            "is_top_role": p_is_top,
            "bio": bio,
            "bio_source": bio_source,
        }
        raw_people.append(person_data)

    # 4. Merge people with the same name in one filing
    merged_people = merge_people_entries(raw_people)

    # 5. Rewrite headline for every filing with people
    current_summary = filing.get("summary")
    current_subject = filing.get("subject", "")
    new_headline = generate_mgmt_headline(merged_people, current_summary, current_subject)

    # 6. Calculate priority
    calculated_priority = determine_priority(merged_people)

    # 7. Save to database
    client = get_client()
    enr = filing.get("enrichment") or {}
    enr["people"] = merged_people

    update_payload: dict[str, Any] = {
        "enrichment": enr,
        "summary": new_headline,
        "priority": calculated_priority,
        "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    client.table("filings").update(update_payload).eq("id", filing_id).execute()

    return {
        "ticker": ticker,
        "id": filing_id,
        "filed_at": filing.get("filed_at"),
        "old_headline": current_summary or current_subject,
        "new_headline": new_headline,
        "priority": calculated_priority,
        "people": merged_people,
    }


def run_pipeline(lookback_days: int = 45, force: bool = False) -> list[dict[str, Any]]:
    """Execute management change enrichment pipeline."""
    mgmt_prompt, bio_prompt = load_prompt_templates()
    company_names = get_company_names()
    filings = find_mgmt_filings(lookback_days=lookback_days, force=force)

    results: list[dict[str, Any]] = []
    for f in filings:
        try:
            res = enrich_mgmt_filing(f, mgmt_prompt, bio_prompt, company_names)
            if res:
                results.append(res)
        except Exception as exc:
            logger.error("Failed processing management change for %s (%s): %s", f.get("ticker"), f.get("id"), exc)

    # Check and apply 7-day duplicate resolution
    deduplicate_filings(results)

    return results


def print_requested_summary(records: list[dict[str, Any]], target_tickers: set[str] | None = None) -> None:
    """Print clean summary showing management filings for target companies."""
    print("\n" + "=" * 90)
    print("FINN MANAGEMENT CHANGE ENRICHMENT SUMMARY")
    print("=" * 90)

    filtered = [r for r in records if (not target_tickers or r["ticker"] in target_tickers)]

    if not filtered:
        print("No management change filings matched the filter criteria.")
        print("=" * 90 + "\n")
        return

    company_names = get_company_names()
    for idx, r in enumerate(filtered, start=1):
        ticker = r["ticker"]
        c_name = company_names.get(ticker, ticker)
        new_headline = r["new_headline"]
        people = r.get("people") or []
        priority = r.get("priority")

        print(f"\n[{idx}] {c_name} ({ticker}) — Priority {priority}")
        print(f"    Headline: {new_headline}")
        print("    People changes & Bios:")
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
    print(f"Total management filings displayed: {len(filtered)}")
    print("=" * 90 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich management change filings for FINN")
    parser.add_argument("--days", type=int, default=45, help="Lookback window in days (default: 45)")
    parser.add_argument("--force", action="store_true", help="Re-process filings even if already enriched")
    args = parser.parse_args()

    records = run_pipeline(lookback_days=args.days, force=args.force)

    # Show only Home First, Nazara, Pidilite, and HDFC Bank
    target_tickers = {"HOMEFIRST", "NAZARA", "PIDILITIND", "HDFCBANK"}
    print_requested_summary(records, target_tickers=target_tickers)


if __name__ == "__main__":
    main()
