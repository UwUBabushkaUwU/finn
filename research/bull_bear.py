"""Generate bull and bear investment case grounded strictly in extracted research facts.

FINN Research Engine - Bull & Bear Case Section.
Input:
  - Promises verdicts and read
  - Numbers section with flags
  - Snapshot section
Each fact carries a distinct ID.
LLM Task: reasoning (cached).
Enforces:
  - 3 points each (or fewer), <= 25 words per point.
  - Every point cites the fact IDs it rests on.
  - Drop any point whose cited IDs do not exist in the facts catalog.
"""

from typing import Any
from pathlib import Path
import sys
import os
import argparse
import datetime
import logging
import json

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
logger = logging.getLogger("bull_bear")


def build_facts_catalog(
    ticker: str,
    promises_data: dict[str, Any] | None,
    numbers_data: dict[str, Any] | None,
    snapshot_data: dict[str, Any] | None,
) -> tuple[dict[str, str], str]:
    """Compile facts catalog where every fact has an ID, returning (catalog_dict, facts_text)."""
    catalog: dict[str, str] = {}
    lines: list[str] = [f"=== RESEARCH FACTS FOR {ticker} ==="]

    # 1. Snapshot facts
    if snapshot_data:
        lines.append("\n[Business Snapshot]")
        what = snapshot_data.get("what_it_does")
        if what:
            fid = "S_WHAT"
            catalog[fid] = f"Business: {what}"
            lines.append(f"- [{fid}] Business: {what}")

        for idx, seg in enumerate(snapshot_data.get("segments", []), start=1):
            s_name = seg.get("name")
            s_share = seg.get("share_of_revenue")
            share_str = f" ({s_share}% of revenue)" if s_share is not None else ""
            fid = f"S_SEG_{idx}"
            text = f"Segment: {s_name}{share_str}"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        cust = snapshot_data.get("customers_and_markets")
        if cust:
            fid = "S_CUSTOMERS"
            catalog[fid] = f"Customers & Markets: {cust}"
            lines.append(f"- [{fid}] Customers & Markets: {cust}")

    # 2. Numbers & Flags facts
    if numbers_data:
        lines.append("\n[Financial Numbers & Flags]")
        snap = numbers_data.get("snapshot", {})

        rev_l = snap.get("latest_quarter_revenue")
        if rev_l:
            fid = "N_REV_LATEST"
            yoy = f", YoY: {rev_l.get('yoy_growth_pct'):+.2f}%" if rev_l.get("yoy_growth_pct") is not None else ""
            text = f"Latest quarter revenue ({rev_l.get('quarter')}): ₹{rev_l.get('value'):,.0f} cr{yoy}"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        pat_l = snap.get("latest_quarter_pat")
        if pat_l:
            fid = "N_PAT_LATEST"
            yoy = f", YoY: {pat_l.get('yoy_growth_pct'):+.2f}%" if pat_l.get("yoy_growth_pct") is not None else ""
            text = f"Latest quarter PAT ({pat_l.get('quarter')}): ₹{pat_l.get('value'):,.0f} cr{yoy}"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        opm_l = snap.get("latest_operating_margin")
        if opm_l and opm_l.get("value") is not None:
            fid = "N_OPM_LATEST"
            text = f"Latest operating margin ({opm_l.get('quarter')}): {opm_l.get('value'):.1f}%"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        ttm_r = snap.get("ttm_revenue")
        if ttm_r and ttm_r.get("value") is not None:
            fid = "N_TTM_REV"
            text = f"TTM revenue: ₹{ttm_r.get('value'):,.0f} cr"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        ttm_p = snap.get("ttm_pat")
        if ttm_p and ttm_p.get("value") is not None:
            fid = "N_TTM_PAT"
            text = f"TTM PAT: ₹{ttm_p.get('value'):,.0f} cr"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        traj = numbers_data.get("trajectory", {})
        if traj.get("revenue_cagr_3y"):
            fid = "N_REV_CAGR_3Y"
            val = traj["revenue_cagr_3y"]["value"]
            text = f"3-year revenue CAGR: {val:.1f}%"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        if traj.get("revenue_cagr_5y"):
            fid = "N_REV_CAGR_5Y"
            val = traj["revenue_cagr_5y"]["value"]
            text = f"5-year revenue CAGR: {val:.1f}%"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        if traj.get("pat_cagr_3y"):
            fid = "N_PAT_CAGR_3Y"
            val = traj["pat_cagr_3y"]["value"]
            text = f"3-year PAT CAGR: {val:.1f}%"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        if traj.get("pat_cagr_5y"):
            fid = "N_PAT_CAGR_5Y"
            val = traj["pat_cagr_5y"]["value"]
            text = f"5-year PAT CAGR: {val:.1f}%"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        bs = numbers_data.get("balance_sheet", {})
        if bs.get("borrowings"):
            fid = "N_BORROWINGS"
            val = bs["borrowings"]["value"]
            text = f"Borrowings: ₹{val:,.0f} cr"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        if bs.get("debt_to_equity") and bs["debt_to_equity"].get("value") is not None:
            fid = "N_DEBT_TO_EQUITY"
            val = bs["debt_to_equity"]["value"]
            text = f"Debt-to-Equity: {val:.2f}"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        if bs.get("working_capital_days"):
            fid = "N_WC_DAYS"
            val = bs["working_capital_days"]["value"]
            text = f"Working capital days: {val:.0f} days"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        if bs.get("cash_conversion_cycle_days"):
            fid = "N_CCC_DAYS"
            val = bs["cash_conversion_cycle_days"]["value"]
            text = f"Cash conversion cycle: {val:.0f} days"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        cq = numbers_data.get("cash_quality", {})
        if cq.get("cash_conversion_3y") and cq["cash_conversion_3y"].get("percentage") is not None:
            fid = "N_CASH_CONV_3Y"
            val = cq["cash_conversion_3y"]["percentage"]
            text = f"3-year cash conversion (CFO/PAT): {val:.1f}%"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

        for idx, fl in enumerate(numbers_data.get("flags", []), start=1):
            fid = f"N_FLAG_{idx}"
            status = "TRIGGERED" if fl.get("triggered") else ("SKIPPED" if fl.get("note") else "OK")
            desc = fl.get("details") or fl.get("note") or fl.get("flag")
            text = f"Flag [{status}] {fl.get('flag')}: {desc}"
            catalog[fid] = text
            lines.append(f"- [{fid}] {text}")

    # 3. Promises facts
    if promises_data:
        lines.append("\n[Management Promises & Guidance]")
        read = promises_data.get("read")
        if read:
            fid = "P_READ"
            catalog[fid] = f"Promises summary: {read}"
            lines.append(f"- [{fid}] Promises summary: {read}")

        for v in promises_data.get("verdicts", []):
            vid = v.get("id")
            if not vid:
                continue
            text = f"Target {vid} ({v.get('applies_to')}): {v.get('promise')} -> Verdict: {v.get('verdict')} [Rev: {v.get('revision_label', 'none')}]. Evidence: {v.get('evidence')}"
            catalog[vid] = text
            lines.append(f"- [{vid}] {text}")

    facts_text = "\n".join(lines)
    return catalog, facts_text


def generate_bull_bear_case(ticker: str) -> dict[str, Any]:
    """Generate bull and bear case for an NSE ticker grounded in research facts."""
    logger.info("Generating Bull & Bear case for %s", ticker)

    # Fetch sections from research table
    sec_rows = select("research", ticker=ticker)
    sec_by_name = {r["section"]: r.get("content") for r in sec_rows}

    promises_content = sec_by_name.get("promises")
    numbers_content = sec_by_name.get("numbers")
    snapshot_content = sec_by_name.get("snapshot")

    if not (promises_content or numbers_content or snapshot_content):
        raise ValueError(f"No research sections found for {ticker} to build bull/bear case.")

    catalog, facts_text = build_facts_catalog(
        ticker=ticker,
        promises_data=promises_content,
        numbers_data=numbers_content,
        snapshot_data=snapshot_content,
    )
    valid_ids = set(catalog.keys())
    logger.info("Compiled %d facts for %s Bull & Bear", len(valid_ids), ticker)

    prompt_path = Path(__file__).resolve().parent / "prompts" / "bull_bear_v1.txt"
    if prompt_path.exists():
        template = prompt_path.read_text(encoding="utf-8")
    else:
        template = (
            "Write the strongest case for and against owning this Indian listed company, using only the facts given (each has an id). "
            "Three points each, at most 25 words per point, each citing the ids it rests on. "
            "Points must be specific to this company, never generic (\"strong management\", \"macro risks\"). "
            "If the facts can't support three points on a side, give fewer.\n"
            "Return JSON: {\"bull\": [{\"point\": \"...\", \"ids\": [...]}], \"bear\": [...]}\n\n"
            "Facts:\n{facts_block}"
        )

    prompt = template.replace("{facts_block}", facts_text)

    response = call_json(
        task="reasoning",
        prompt=prompt,
        prompt_version="bull_bear_v1",
        use_cache=True,
    )

    if not isinstance(response, dict):
        response = {"bull": [], "bear": []}

    raw_bull = response.get("bull", [])
    raw_bear = response.get("bear", [])

    clean_bull: list[dict[str, Any]] = []
    clean_bear: list[dict[str, Any]] = []

    # Filter and validate Bull points: drop any point whose ids don't exist
    for p in raw_bull:
        if not isinstance(p, dict):
            continue
        pt = (p.get("point") or "").strip()
        cites = p.get("ids") or []
        if isinstance(cites, str):
            cites = [cites]
        if not cites:
            continue
        # Drop if any cited ID doesn't exist
        if any(c_id not in valid_ids for c_id in cites):
            logger.warning("Dropping bull point with invalid IDs %s: %s", cites, pt)
            continue
        # Enforce <= 25 words
        words = pt.split()
        if len(words) > 25:
            pt = " ".join(words[:25])
        clean_bull.append({"point": pt, "ids": cites})
        if len(clean_bull) >= 3:
            break

    # Filter and validate Bear points: drop any point whose ids don't exist
    for p in raw_bear:
        if not isinstance(p, dict):
            continue
        pt = (p.get("point") or "").strip()
        cites = p.get("ids") or []
        if isinstance(cites, str):
            cites = [cites]
        if not cites:
            continue
        # Drop if any cited ID doesn't exist
        if any(c_id not in valid_ids for c_id in cites):
            logger.warning("Dropping bear point with invalid IDs %s: %s", cites, pt)
            continue
        # Enforce <= 25 words
        words = pt.split()
        if len(words) > 25:
            pt = " ".join(words[:25])
        clean_bear.append({"point": pt, "ids": cites})
        if len(clean_bear) >= 3:
            break

    result_data = {
        "bull": clean_bull,
        "bear": clean_bear,
    }

    # Save to research table
    upsert(
        "research",
        {
            "ticker": ticker,
            "section": "bull_bear",
            "content": result_data,
            "sources": [
                {"section": "promises"},
                {"section": "numbers"},
                {"section": "snapshot"},
            ],
            "model": MODEL_IDS.get("reasoning", "gemini-flash-latest"),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        on_conflict="ticker,section",
    )
    logger.info("Saved bull_bear section for %s", ticker)

    return result_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Bull & Bear investment case.")
    parser.add_argument("--ticker", required=True, help="NSE ticker symbol (e.g. DIXON)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    data = generate_bull_bear_case(args.ticker)
    print("=" * 70)
    print(f"BULL & BEAR CASE: {args.ticker}")
    print("=" * 70)
    print("\nBULL CASE:")
    for b in data.get("bull", []):
        print(f"  + {b.get('point')} (cites: {', '.join(b.get('ids', []))})")
    print("\nBEAR CASE:")
    for b in data.get("bear", []):
        print(f"  - {b.get('point')} (cites: {', '.join(b.get('ids', []))})")
    print("=" * 70)

