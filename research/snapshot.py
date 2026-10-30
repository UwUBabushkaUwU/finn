"""Extract business overview, segments, and market snapshot from Annual Reports.

FINN Research Engine - Business Snapshot Section.
Uses keyword scoring (no embeddings) across annual report pages,
selects the top 12 relevant pages, and extracts concise structured facts
using the bulk LLM model.
"""

from typing import Any
from pathlib import Path
import sys
import os
import argparse
import datetime
import logging
import re

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure utf-8 stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pipeline.config import MODEL_IDS
from pipeline.db import select, upsert
from pipeline.llm import call_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("snapshot")

KEYWORD_WEIGHTS = {
    "business overview": 5,
    "revenue mix": 5,
    "segment reporting": 4,
    "management discussion and analysis": 4,
    "management discussion": 4,
    "products": 2,
    "segment": 2,
    "operational highlights": 2,
    "principal activities": 2,
}


def score_pages_by_keywords(pages: list[str]) -> list[int]:
    """Score pages by keyword occurrences and return top <= 12 page numbers (1-indexed)."""
    scored: list[tuple[int, int]] = []  # (score, 1-indexed page_num)

    for idx, page_text in enumerate(pages):
        if not page_text or len(page_text.strip()) < 50:
            continue
        p_lower = page_text.lower()
        score = 0
        for kw, weight in KEYWORD_WEIGHTS.items():
            count = p_lower.count(kw)
            if count > 0:
                score += min(count, 5) * weight

        if score > 0:
            scored.append((score, idx + 1))

    # Sort descending by score, take top 12, then sort ascending by page number
    scored.sort(key=lambda x: -x[0])
    top_pages = sorted([p for _, p in scored[:12]])
    return top_pages


def build_business_snapshot(ticker: str) -> dict[str, Any]:
    """Build business snapshot for an NSE ticker from its annual report."""
    logger.info("Building business snapshot for %s", ticker)
    docs = select("documents", ticker=ticker, kind="annual_report")
    if not docs:
        raise ValueError(f"No annual report document found for {ticker} in documents table.")

    # Sort by event_date desc, period desc to get latest
    sorted_docs = sorted(
        docs,
        key=lambda d: (str(d.get("event_date") or ""), str(d.get("period") or "")),
        reverse=True,
    )
    doc = sorted_docs[0]
    pages: list[str] = doc.get("pages", [])
    if not pages:
        raise ValueError(f"Annual report for {ticker} has 0 pages.")

    selected_page_nums = score_pages_by_keywords(pages)
    if not selected_page_nums:
        # Fallback to first 12 pages if keyword match yields nothing
        selected_page_nums = list(range(1, min(13, len(pages) + 1)))

    logger.info("Selected %d pages for %s snapshot: %s", len(selected_page_nums), ticker, selected_page_nums)

    # Format pages for the prompt
    formatted_pages = []
    for p_num in selected_page_nums:
        p_text = pages[p_num - 1].strip()
        formatted_pages.append(f"--- Page {p_num} ---\n{p_text}")
    pages_block = "\n\n".join(formatted_pages)

    prompt_path = Path(__file__).resolve().parent / "prompts" / "snapshot_v1.txt"
    if prompt_path.exists():
        template = prompt_path.read_text(encoding="utf-8")
    else:
        template = (
            "From these pages of an Indian listed company's annual report, describe the business. Use only these pages.\n"
            "Return JSON: {\"what_it_does\": at most 35 words,\n"
            " \"segments\": [{\"name\": \"...\", \"share_of_revenue\": number or null, \"page\": n}],\n"
            " \"customers_and_markets\": at most 25 words or null,\n"
            " \"pages_used\": [...]}\n"
            "If a figure isn't printed, use null. No marketing language.\n\n"
            "Pages:\n{pages_text}"
        )

    prompt = template.replace("{pages_text}", pages_block)

    response = call_json(
        task="bulk",
        prompt=prompt,
        prompt_version="snapshot_v1",
        use_cache=True,
    )

    if not isinstance(response, dict):
        response = {
            "what_it_does": "Information not available.",
            "segments": [],
            "customers_and_markets": None,
            "pages_used": selected_page_nums,
        }

    # Ensure pages_used is populated
    if not response.get("pages_used"):
        response["pages_used"] = selected_page_nums

    # Clean word counts if needed
    what_it_does = (response.get("what_it_does") or "").strip()
    words = what_it_does.split()
    if len(words) > 35:
        what_it_does = " ".join(words[:35])
    response["what_it_does"] = what_it_does

    cust_markets = response.get("customers_and_markets")
    if cust_markets and isinstance(cust_markets, str):
        cm_s = cust_markets.strip()
        if cm_s.lower() in ("null", "none", "n/a", "na", "nil", "undefined", "—", "-", "not available", "information not available"):
            response["customers_and_markets"] = None
        else:
            cm_words = cm_s.split()
            if len(cm_words) > 25:
                cm_s = " ".join(cm_words[:25])
            response["customers_and_markets"] = cm_s
    else:
        response["customers_and_markets"] = None

    # Save to research table
    upsert(
        "research",
        {
            "ticker": ticker,
            "section": "snapshot",
            "content": response,
            "sources": [
                {
                    "kind": "annual_report",
                    "period": doc.get("period"),
                    "url": doc.get("url"),
                    "pages": response.get("pages_used", selected_page_nums),
                }
            ],
            "model": MODEL_IDS.get("bulk", "gemini-flash-lite-latest"),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        on_conflict="ticker,section",
    )
    logger.info("Saved snapshot section for %s", ticker)

    return response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract business snapshot from annual report.")
    parser.add_argument("--ticker", required=True, help="NSE ticker symbol (e.g. DIXON)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    data = build_business_snapshot(args.ticker)
    print("=" * 70)
    print(f"BUSINESS SNAPSHOT: {args.ticker}")
    print("=" * 70)
    print(f"What it does: {data.get('what_it_does')}")
    print("\nSegments:")
    for s in data.get("segments", []):
        share_str = f" ({s.get('share_of_revenue')}%)" if s.get("share_of_revenue") is not None else ""
        print(f"  - {s.get('name')}{share_str} [p.{s.get('page')}]")
    print(f"\nCustomers & Markets: {data.get('customers_and_markets')}")
    print(f"Pages used: {data.get('pages_used')}")
    print("=" * 70)

