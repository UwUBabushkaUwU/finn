"""Filing classifier for FINN.

Pre-filters routine paperwork using rule-based subjects, then classifies
material announcements with Google Gemini (task "bulk") in batches of 20.
Saves category, priority, summary (headline), and enrichment into the filings table.
"""

from typing import Any
from pathlib import Path
import sys
import json
import logging
import argparse
import datetime

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import PIPELINE_DIR
from pipeline.db import get_client, select, upsert
from pipeline.llm import call_json, get_cache_stats, reset_cache_stats

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("classify")

PROMPT_VERSION = "v1"

ALLOWED_CATEGORIES = {
    "results",
    "m&a",
    "fund_raise",
    "management_change",
    "litigation",
    "insider_trading",
    "earnings_call",
    "investor_meetings",
    "credit_rating",
    "dividend",
    "bonus_split",
    "capex",
    "press_release",
    "postal_ballot",
    "agm_egm",
    "pledging",
    "unclassified",
}

# Map normalized lowercase to canonical names
CATEGORY_MAP = {
    "results": "results",
    "m&a": "M&A",
    "fund_raise": "fund_raise",
    "management_change": "management_change",
    "litigation": "litigation",
    "insider_trading": "insider_trading",
    "earnings_call": "earnings_call",
    "investor_meetings": "investor_meetings",
    "credit_rating": "credit_rating",
    "dividend": "dividend",
    "bonus_split": "bonus_split",
    "capex": "capex",
    "press_release": "press_release",
    "postal_ballot": "postal_ballot",
    "agm_egm": "agm_egm",
    "pledging": "pledging",
    "unclassified": "unclassified",
}


def load_routine_subjects() -> set[str]:
    """Load routine paperwork subject lines from pipeline/prompts/routine_subjects.txt."""
    path = PIPELINE_DIR / "prompts" / "routine_subjects.txt"
    if not path.exists():
        logger.warning("Routine subjects file not found at %s", path)
        return set()

    subjects = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                subjects.add(cleaned.lower())
    return subjects


def load_prompt_template() -> str:
    """Load classification prompt template."""
    path = PIPELINE_DIR / "prompts" / f"classify_{PROMPT_VERSION}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Classification prompt not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_company_names() -> dict[str, str]:
    """Map ticker to company name from companies table."""
    companies = select("companies")
    return {c["ticker"]: c.get("name", c["ticker"]) for c in companies}


def fetch_filings(all_filings: bool, ticker: str | None) -> list[dict[str, Any]]:
    """Fetch unclassified (or all) filings from Supabase."""
    client = get_client()
    query = client.table("filings").select("*")

    if not all_filings:
        query = query.is_("processed_at", "null")
    if ticker:
        query = query.eq("ticker", ticker.upper())

    # Range-paginate up to 5,000 filings
    all_data = []
    page_size = 1000
    start = 0

    while True:
        res = query.order("filed_at", desc=True).range(start, start + page_size - 1).execute()
        rows = res.data or []
        all_data.extend(rows)
        if len(rows) < page_size:
            break
        start += page_size

    return all_data


def is_routine_subject(subject: str, routine_set: set[str]) -> bool:
    """Check if subject matches routine paperwork rules."""
    subj_clean = (subject or "").strip().lower()
    return subj_clean in routine_set


def validate_item(item: Any, expected_id: str) -> dict[str, Any] | None:
    """Validate a single item from the model output."""
    if not isinstance(item, dict):
        return None

    item_id = str(item.get("id") or "").strip()
    if item_id != expected_id:
        return None

    cat_raw = str(item.get("category") or "").strip().lower()
    if cat_raw not in ALLOWED_CATEGORIES:
        return None
    canonical_cat = CATEGORY_MAP.get(cat_raw, "unclassified")

    priority = item.get("priority")
    try:
        priority_int = int(priority)
        if priority_int not in (1, 2, 3):
            return None
    except (TypeError, ValueError):
        return None

    headline = item.get("headline")
    if headline is not None:
        headline = str(headline).strip()
    if priority_int == 3:
        headline = None

    why = item.get("why")
    why_str = str(why).strip() if why is not None else None

    return {
        "id": expected_id,
        "category": canonical_cat,
        "priority": priority_int,
        "headline": headline,
        "why": why_str,
    }


def classify_single_fallback(
    item_payload: dict[str, Any], prompt_template: str
) -> dict[str, Any]:
    """Retry a single item alone once; fall back to priority 2 if it still fails."""
    single_json = json.dumps([item_payload], indent=2)
    prompt = prompt_template.replace("{filings_json}", single_json)

    try:
        resp = call_json("bulk", prompt, PROMPT_VERSION)
        if isinstance(resp, list) and len(resp) > 0:
            valid = validate_item(resp[0], item_payload["id"])
            if valid:
                return valid
    except Exception as exc:
        logger.warning("Single retry failed for %s: %s", item_payload["id"], exc)

    return {
        "id": item_payload["id"],
        "category": "unclassified",
        "priority": 2,
        "headline": "Couldn't classify — open the PDF",
        "why": "Fallback: item failed schema validation",
    }


def classify_batch(
    batch_filings: list[dict[str, Any]],
    company_names: dict[str, str],
    prompt_template: str,
) -> list[dict[str, Any]]:
    """Send a batch of up to 20 filings to the bulk LLM model."""
    payload = []
    for f in batch_filings:
        desc = (f.get("description") or f.get("subject") or "").strip()
        payload.append({
            "id": f["id"],
            "ticker": f["ticker"],
            "company": company_names.get(f["ticker"], f["ticker"]),
            "subject": f.get("subject", ""),
            "text": desc[:1500],
        })

    prompt = prompt_template.replace("{filings_json}", json.dumps(payload, indent=2))

    results_by_id: dict[str, dict[str, Any]] = {}
    try:
        resp = call_json("bulk", prompt, PROMPT_VERSION)
        if isinstance(resp, list):
            for obj in resp:
                if isinstance(obj, dict) and "id" in obj:
                    results_by_id[str(obj["id"]).strip()] = obj
    except Exception as exc:
        logger.warning("Batch LLM call failed: %s", exc)

    final_results = []
    for item_payload in payload:
        fid = item_payload["id"]
        raw_obj = results_by_id.get(fid)
        valid = validate_item(raw_obj, fid) if raw_obj else None

        if valid:
            final_results.append(valid)
        else:
            logger.info("Item %s missing/invalid in batch. Retrying alone once...", fid)
            fallback_res = classify_single_fallback(item_payload, prompt_template)
            final_results.append(fallback_res)

    return final_results


def run_classification(
    all_filings: bool = False,
    ticker: str | None = None,
    batch_size: int = 20,
) -> dict[str, Any]:
    """Execute rule pre-filtering and LLM classification on filings."""
    reset_cache_stats()

    filings = fetch_filings(all_filings, ticker)
    if not filings:
        logger.info("No filings to classify.")
        return {
            "total_processed": 0,
            "rule_count": 0,
            "llm_count": 0,
            "llm_calls": 0,
            "cache_hits": 0,
            "priority_counts": {1: 0, 2: 0, 3: 0},
        }

    logger.info("Loaded %d filings for classification.", len(filings))

    routine_subjects = load_routine_subjects()
    company_names = get_company_names()
    prompt_template = load_prompt_template()

    rule_updates: list[dict[str, Any]] = []
    llm_filings: list[dict[str, Any]] = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Step 1: Rule pre-filter
    for f in filings:
        if is_routine_subject(f.get("subject", ""), routine_subjects):
            updated_row = dict(f)
            updated_row["category"] = "unclassified"
            updated_row["priority"] = 3
            updated_row["summary"] = None
            updated_row["enrichment"] = {"why": "Routine paperwork per subject rule"}
            updated_row["processed_at"] = now_iso
            rule_updates.append(updated_row)
        else:
            llm_filings.append(f)

    logger.info(
        "Rule pre-filter: %d filings classified as routine (priority 3). %d sent to LLM.",
        len(rule_updates),
        len(llm_filings),
    )

    # Step 2: LLM classification in batches
    llm_updates: list[dict[str, Any]] = []
    for i in range(0, len(llm_filings), batch_size):
        batch = llm_filings[i : i + batch_size]
        batch_results = classify_batch(batch, company_names, prompt_template)
        results_map = {res["id"]: res for res in batch_results}

        for f in batch:
            res = results_map.get(f["id"])
            updated_row = dict(f)
            if res:
                updated_row["category"] = res["category"]
                updated_row["priority"] = res["priority"]
                updated_row["summary"] = res["headline"]
                updated_row["enrichment"] = {"why": res["why"]}
            else:
                updated_row["category"] = "unclassified"
                updated_row["priority"] = 2
                updated_row["summary"] = "Couldn't classify — open the PDF"
                updated_row["enrichment"] = {"why": "Missing model result"}
            updated_row["processed_at"] = now_iso
            llm_updates.append(updated_row)

    # Step 3: Save all updates to Supabase
    all_to_save = rule_updates + llm_updates
    save_batch_size = 100
    for i in range(0, len(all_to_save), save_batch_size):
        save_batch = all_to_save[i : i + save_batch_size]
        upsert("filings", save_batch, on_conflict="id")

    stats = get_cache_stats()

    priority_counts = {1: 0, 2: 0, 3: 0}
    for item in all_to_save:
        p = item.get("priority")
        if p in priority_counts:
            priority_counts[p] += 1

    summary = {
        "total_processed": len(all_to_save),
        "rule_count": len(rule_updates),
        "llm_count": len(llm_updates),
        "llm_calls": stats.get("real_calls", 0),
        "cache_hits": stats.get("cache_hits", 0),
        "priority_counts": priority_counts,
    }

    print("\n================ Filing Classifier Summary ================")
    print(f"Filings processed : {summary['total_processed']}")
    print(f"  - By rule       : {summary['rule_count']}")
    print(f"  - By LLM        : {summary['llm_count']}")
    print(f"LLM calls made    : {summary['llm_calls']}")
    print(f"Cache hits        : {summary['cache_hits']}")
    print("\nPriority distribution:")
    print(f"  - Priority 1    : {priority_counts[1]}")
    print(f"  - Priority 2    : {priority_counts[2]}")
    print(f"  - Priority 3    : {priority_counts[3]}")
    print("===========================================================\n")

    return summary


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Classify filings using rule pre-filter and Gemini.")
    parser.add_argument("--all", action="store_true", help="Reclassify all filings (even if already processed)")
    parser.add_argument("--ticker", type=str, default=None, help="Specific ticker to classify")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size for LLM calls (default: 20)")
    args = parser.parse_args()

    run_classification(all_filings=args.all, ticker=args.ticker, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
