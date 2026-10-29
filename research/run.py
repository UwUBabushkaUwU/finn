"""FINN Research Engine - Master Orchestrator and Job Queue Runner.

Executes research pipeline in strict order:
  1. build_corpus: fetches financials and primary PDF documents from screener.in.
  2. promises: extracts, verifies, and judges management guidance vs results.
  3. numbers: computes deterministic financial snapshot, trajectory, balance sheet, cash quality, and flags.
  4. snapshot: extracts business overview, segments, and customers/markets from annual report.
  5. bull_bear: compiles research facts and writes 3 bull & 3 bear points citing fact IDs.
  6. meta: saves section meta with company name, documents used, and generated_at.

Updates research_jobs table throughout execution.
One failing step does not erase earlier completed sections.
Supports:
  --ticker SYM: runs pipeline for a specific NSE symbol.
  --pending: finds and processes every research_jobs row with status 'queued'.
"""

from typing import Any
from pathlib import Path
import sys
import argparse
import datetime
import logging
import traceback

# Prevent shadowing of standard library 'numbers'
_script_dir = str(Path(__file__).resolve().parent)
while _script_dir in sys.path:
    sys.path.remove(_script_dir)

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

from pipeline.db import select, upsert
from research.build_corpus import build_corpus_for_ticker
from research.promises import run_promises_for_ticker
from research.numbers import compute_numbers_for_ticker
from research.snapshot import build_business_snapshot
from research.bull_bear import generate_bull_bear_case

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("research_run")


def update_job_status(
    ticker: str,
    status: str,
    step: str | None = None,
    error: str | None = None,
    set_started: bool = False,
    set_finished: bool = False,
) -> None:
    """Update research_jobs row in Supabase."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    job_data: dict[str, Any] = {
        "ticker": ticker,
        "status": status,
        "step": step,
        "error": error,
    }

    # Ensure requested_at is populated if inserting new job
    existing = select("research_jobs", ticker=ticker)
    if not existing:
        job_data["requested_at"] = now_iso

    if set_started:
        job_data["started_at"] = now_iso
    if set_finished:
        job_data["finished_at"] = now_iso

    try:
        upsert("research_jobs", job_data, on_conflict="ticker")
    except Exception as exc:
        logger.warning("Failed to update research_jobs for %s: %s", ticker, exc)


def save_section_meta(ticker: str) -> None:
    """Save 'meta' section in research table with company name, documents used, and generated_at."""
    # Find company name
    comp_rows = select("companies", ticker=ticker)
    company_name = comp_rows[0].get("name", ticker) if comp_rows else ticker

    # Collect documents used
    doc_rows = select("documents", ticker=ticker)
    docs_used = [
        {
            "kind": d.get("kind"),
            "period": d.get("period"),
            "url": d.get("url"),
        }
        for d in doc_rows
    ]

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    meta_content = {
        "company_name": company_name,
        "documents_used": docs_used,
        "generated_at": now_iso,
    }

    upsert(
        "research",
        {
            "ticker": ticker,
            "section": "meta",
            "content": meta_content,
            "sources": docs_used,
            "model": "python",
            "generated_at": now_iso,
        },
        on_conflict="ticker,section",
    )
    logger.info("Saved meta section for %s (%d documents used)", ticker, len(docs_used))


def run_pipeline_for_ticker(ticker: str) -> bool:
    """Execute full research pipeline in order for a ticker."""
    ticker = ticker.strip().upper()
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"STARTING RESEARCH RUN FOR: {ticker}")
    print(f"{sep}\n")

    # Step 1: Finding filings and transcripts (corpus)
    step_1 = "Finding filings and transcripts"
    update_job_status(ticker, status="running", step=step_1, error=None, set_started=True)

    try:
        logger.info("[Step 1/6] %s for %s...", step_1, ticker)
        build_corpus_for_ticker(ticker)
    except Exception as exc:
        err = str(exc)
        logger.error("Corpus building failed for %s: %s", ticker, err)
        update_job_status(ticker, status="failed", step=step_1, error=err, set_finished=True)
        return False

    # Step 2 & 3: Reading earnings calls & Checking promises against results
    try:
        logger.info("[Step 2 & 3/6] Reading concalls and checking promises for %s...", ticker)
        run_promises_for_ticker(
            ticker,
            on_step=lambda st: update_job_status(ticker, status="running", step=st),
        )
    except Exception as exc:
        err = str(exc)
        logger.error("Promises failed for %s: %s", ticker, err)
        update_job_status(ticker, status="failed", step="Checking promises against results", error=err, set_finished=True)
        return False

    # Step 4: Crunching the numbers
    step_4 = "Crunching the numbers"
    try:
        update_job_status(ticker, status="running", step=step_4)
        logger.info("[Step 4/6] %s for %s...", step_4, ticker)
        compute_numbers_for_ticker(ticker)
    except Exception as exc:
        err = str(exc)
        logger.error("Numbers failed for %s: %s", ticker, err)
        update_job_status(ticker, status="failed", step=step_4, error=err, set_finished=True)
        return False

    # Step 5: Reading the annual report (snapshot)
    step_5 = "Reading the annual report"
    try:
        update_job_status(ticker, status="running", step=step_5)
        logger.info("[Step 5/6] %s for %s...", step_5, ticker)
        build_business_snapshot(ticker)
    except Exception as exc:
        err = str(exc)
        logger.error("Snapshot failed for %s: %s", ticker, err)
        update_job_status(ticker, status="failed", step=step_5, error=err, set_finished=True)
        return False

    # Step 6: Writing the bull and bear case
    step_6 = "Writing the bull and bear case"
    try:
        update_job_status(ticker, status="running", step=step_6)
        logger.info("[Step 6/6] %s for %s...", step_6, ticker)
        generate_bull_bear_case(ticker)
    except Exception as exc:
        err = str(exc)
        logger.error("Bull & Bear failed for %s: %s", ticker, err)
        update_job_status(ticker, status="failed", step=step_6, error=err, set_finished=True)
        return False

    # Meta
    try:
        save_section_meta(ticker)
    except Exception as exc:
        logger.warning("Error saving section meta for %s: %s", ticker, exc)

    # Step 7: Completed
    update_job_status(ticker, status="done", step="completed", error=None, set_finished=True)
    logger.info("Research run for %s successfully completed!", ticker)
    return True


def run_pending_jobs() -> int:
    """Process all queued research jobs in research_jobs table."""
    logger.info("Checking for pending queued research jobs...")
    queued_jobs = select("research_jobs", status="queued")
    if not queued_jobs:
        print("No pending queued research jobs found.")
        return 0

    print(f"Found {len(queued_jobs)} queued job(s): {[j.get('ticker') for j in queued_jobs]}")
    success_count = 0
    for job in queued_jobs:
        t = job.get("ticker")
        if not t:
            continue
        ok = run_pipeline_for_ticker(t)
        if ok:
            success_count += 1

    print(f"\nPending queue run completed: {success_count}/{len(queued_jobs)} jobs succeeded.")
    return success_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FINN Research Engine Orchestrator.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="NSE ticker symbol to process (e.g. DIXON)")
    group.add_argument("--pending", action="store_true", help="Process all queued research jobs")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.pending:
        run_pending_jobs()
    elif args.ticker:
        success = run_pipeline_for_ticker(args.ticker)
        if not success:
            sys.exit(1)

