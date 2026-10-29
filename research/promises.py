"""Extract, verify, and judge management promises from concall transcripts.

FINN Research Engine - Promises & Guidance Tracker.
Three steps:
  1. Extract guidance and reported figures using bulk LLM (once per transcript).
  2. Verify all extracted quotes in Python (no LLM) and build guidance timeline.
  3. Judge delivery using reasoning LLM (once per company) against computed financials.
"""

from typing import Any
from pathlib import Path
import sys
import os
import io
import time
import re
import difflib
import argparse
import datetime
import logging
import requests

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import MODEL_IDS
from pipeline.db import get_client, upsert, select
from pipeline.llm import call_json

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("promises")


def normalize_text(text: str) -> str:
    """Normalize whitespace and quotation characters for reliable matching."""
    if not text:
        return ""
    # Standardize single and double quotation marks
    text = re.sub(r"[\u2018\u2019\u201a\u201b\u2032']", "'", text)
    text = re.sub(r'[\u201c\u201d\u201e\u201f\u2033"]', '"', text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def verify_quote_on_pages(quote: str, pages: list[str], page_num: int) -> bool:
    """Verify that quote appears on the specified page of the transcript.
    
    Checks exact substring match or sliding window difflib match >= 90%.
    Also checks adjacent pages (page_num - 1, page_num + 1) to handle 1-off indexing.
    """
    if not quote or not pages:
        return False

    norm_quote = normalize_text(quote)
    if not norm_quote:
        return False

    # Check target page and adjacent pages (1-indexed input)
    candidate_indices = [page_num - 1, page_num - 2, page_num]
    q_len = len(norm_quote)

    for idx in candidate_indices:
        if 0 <= idx < len(pages):
            page_text = normalize_text(pages[idx])
            if norm_quote in page_text:
                return True

            # Sliding window match with difflib
            step = max(1, q_len // 3)
            for i in range(0, max(1, len(page_text) - q_len + 1), step):
                window = page_text[i : i + q_len + 20]
                ratio = difflib.SequenceMatcher(None, norm_quote, window).ratio()
                if ratio >= 0.90:
                    return True

    return False


def load_claims_prompt_template() -> str:
    """Load claims extraction prompt from research/prompts/claims_v1.txt."""
    path = PROJECT_ROOT / "research" / "prompts" / "claims_v1.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_verdicts_prompt_template() -> str:
    """Load verdicts evaluation prompt from research/prompts/verdicts_v1.txt."""
    path = PROJECT_ROOT / "research" / "prompts" / "verdicts_v1.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def format_transcript_with_page_markers(pages: list[str]) -> str:
    """Format transcript pages with [p.1], [p.2], ... markers."""
    chunks = []
    for i, p_text in enumerate(pages, start=1):
        chunks.append(f"[p.{i}]\n{p_text.strip()}")
    return "\n\n".join(chunks)


def extract_claims_from_transcript(doc: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Extract guidance and reported figures using cheap model (bulk task)."""
    period = doc.get("period", "Unknown")
    pages = doc.get("pages") or []
    text_ok = doc.get("text_ok", True)
    template = load_claims_prompt_template()

    pdf_bytes: bytes | None = None
    if text_ok and pages:
        transcript_text = format_transcript_with_page_markers(pages)
        prompt = template.replace("{period}", period).replace("{transcript_text}", transcript_text)
    else:
        # If text_ok is false, download raw PDF bytes
        logger.info("Transcript text_ok=False for %s; fetching raw PDF", period)
        url = doc["url"]
        resp = requests.get(url, timeout=30)
        pdf_bytes = resp.content
        prompt = template.replace("{period}", period).replace("{transcript_text}", "[Attached PDF Document]")

    # Execute LLM call via pipeline.llm.call_json (cached by model + prompt_version + prompt)
    response = call_json(
        task="bulk",
        prompt=prompt,
        prompt_version="claims_v1",
        pdf_bytes=pdf_bytes,
        use_cache=True,
    )

    if not isinstance(response, dict):
        logger.warning("Unexpected non-dict response from LLM: %s", response)
        return {"guidance": [], "reported": []}

    guidance = response.get("guidance", [])
    reported = response.get("reported", [])
    return {
        "guidance": guidance if isinstance(guidance, list) else [],
        "reported": reported if isinstance(reported, list) else [],
    }


def verify_extracted_claims(
    doc: dict[str, Any], raw_claims: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """Step 2: Verify every quote against transcript pages in Python.
    
    Returns (verified_guidance, verified_reported, total_extracted, total_verified).
    """
    pages = doc.get("pages") or []
    doc_id = doc["id"]
    period = doc.get("period", "")
    event_date = doc.get("event_date")

    raw_guidance = raw_claims.get("guidance", [])
    raw_reported = raw_claims.get("reported", [])

    total_extracted = len(raw_guidance) + len(raw_reported)
    verified_guidance = []
    verified_reported = []

    for item in raw_guidance:
        quote = item.get("quote", "")
        page = item.get("page", 1)
        if isinstance(page, str) and page.isdigit():
            page = int(page)
        elif not isinstance(page, int):
            page = 1

        if verify_quote_on_pages(quote, pages, page):
            item_copy = dict(item)
            item_copy["document_id"] = doc_id
            item_copy["period_made"] = period
            item_copy["event_date"] = event_date
            verified_guidance.append(item_copy)
        else:
            logger.info("Dropped unverified guidance quote on %s [p.%d]: %s", period, page, quote[:60])

    for item in raw_reported:
        quote = item.get("quote", "")
        page = item.get("page", 1)
        if isinstance(page, str) and page.isdigit():
            page = int(page)
        elif not isinstance(page, int):
            page = 1

        if verify_quote_on_pages(quote, pages, page):
            item_copy = dict(item)
            item_copy["document_id"] = doc_id
            item_copy["period_reported"] = period
            item_copy["event_date"] = event_date
            verified_reported.append(item_copy)
        else:
            logger.info("Dropped unverified reported quote on %s [p.%d]: %s", period, page, quote[:60])

    total_verified = len(verified_guidance) + len(verified_reported)
    return verified_guidance, verified_reported, total_extracted, total_verified


def build_guidance_timeline(guidance_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build guidance timeline across quarters grouped by (metric, applies_to)."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for g in guidance_items:
        metric = g.get("metric", "").strip().lower()
        applies_to = g.get("applies_to", "").strip()
        if not metric or not applies_to:
            continue
        key = (metric, applies_to)
        if key not in groups:
            groups[key] = []
        groups[key].append(g)

    timeline_entries = []
    for (metric, applies_to), items in groups.items():
        # Sort items by event date / period made
        items_sorted = sorted(items, key=lambda x: str(x.get("event_date", "")))
        steps = []
        for it in items_sorted:
            target = it.get("target") or {}
            val_str = ""
            if target.get("value") is not None:
                val_str = f"{target['value']}{target.get('unit', '')}"
            elif target.get("low") is not None and target.get("high") is not None:
                val_str = f"{target['low']}–{target['high']}{target.get('unit', '')}"
            elif it.get("statement"):
                val_str = it["statement"]
            else:
                val_str = "target updated"

            steps.append(f"{val_str} ({it.get('period_made', '')})")

        timeline_str = f"{applies_to} {metric}: " + " → ".join(steps)
        timeline_entries.append({
            "metric": metric,
            "applies_to": applies_to,
            "evolution": timeline_str,
            "items": items_sorted,
        })

    return timeline_entries


def compute_quarterly_financial_numbers(financials_row: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute QoQ, YoY, H1 YoY, and trailing 4 quarter totals with unique N-ids."""
    tables = financials_row.get("tables", {})
    q_table = tables.get("quarterly_results", {})
    columns = q_table.get("columns", [])
    rows = q_table.get("rows", [])

    if not columns or not rows:
        return []

    # Map column headers to quarter labels
    # e.g. Sep 2026 -> Q2 FY27, Jun 2026 -> Q1 FY27, Mar 2026 -> Q4 FY26, Dec 2025 -> Q3 FY26
    month_map = {
        "jun": ("Q1", 1),
        "sep": ("Q2", 1),
        "dec": ("Q3", 1),
        "mar": ("Q4", 0),
    }

    col_labels = []
    for col in columns:
        parts = col.split()
        if len(parts) >= 2 and parts[1].isdigit():
            m_prefix = parts[0][:3].lower()
            year_int = int(parts[1])
            if m_prefix in month_map:
                q_name, add_year = month_map[m_prefix]
                fy_code = f"FY{str(year_int + add_year)[-2:]}"
                col_labels.append(f"{q_name} {fy_code} ({col})")
            else:
                col_labels.append(col)
        else:
            col_labels.append(col)

    n_items: list[dict[str, Any]] = []
    counter = 1

    for row in rows:
        label = row.get("label", "")
        values = row.get("values", [])
        num_cols = len(columns)

        for i in range(num_cols):
            v_curr = values[i] if i < len(values) else None
            if v_curr is None:
                continue

            q_label = col_labels[i]
            parts = [f"{label} {q_label} = {v_curr:,.1f}"]

            # QoQ growth
            if i > 0:
                v_prev = values[i - 1] if (i - 1) < len(values) else None
                if v_prev is not None and v_prev != 0:
                    qoq = ((v_curr - v_prev) / abs(v_prev)) * 100.0
                    parts.append(f"{qoq:+.1f}% QoQ vs {col_labels[i - 1]}")

            # YoY growth (4 quarters back)
            if i >= 4:
                v_yoy = values[i - 4] if (i - 4) < len(values) else None
                if v_yoy is not None and v_yoy != 0:
                    yoy = ((v_curr - v_yoy) / abs(v_yoy)) * 100.0
                    parts.append(f"{yoy:+.1f}% YoY vs {col_labels[i - 4]}")

            desc = "; ".join(parts)
            n_items.append({
                "id": f"N{counter}",
                "description": desc,
                "label": label,
                "period": q_label,
                "value": v_curr,
            })
            counter += 1

        # Trailing 4 Quarters total (TTM) vs previous 4 quarters
        if num_cols >= 8:
            last_4 = [values[j] for j in range(num_cols - 4, num_cols) if j < len(values) and values[j] is not None]
            prev_4 = [values[j] for j in range(num_cols - 8, num_cols - 4) if j < len(values) and values[j] is not None]
            if len(last_4) == 4 and len(prev_4) == 4:
                sum_last = sum(last_4)
                sum_prev = sum(prev_4)
                if sum_prev != 0:
                    pct = ((sum_last - sum_prev) / abs(sum_prev)) * 100.0
                    ttm_desc = (
                        f"{label} Trailing 4 Quarters ({col_labels[num_cols-4]} to {col_labels[num_cols-1]}) "
                        f"= {sum_last:,.1f} vs prev 4Q {sum_prev:,.1f} ({pct:+.1f}% YoY)"
                    )
                    n_items.append({
                        "id": f"N{counter}",
                        "description": ttm_desc,
                        "label": label,
                        "period": "TTM",
                        "value": sum_last,
                    })
                    counter += 1

    return n_items


def judge_promises_for_company(
    ticker: str,
    guidance_items: list[dict[str, Any]],
    timeline_entries: list[dict[str, Any]],
    reported_items: list[dict[str, Any]],
    n_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Step 3: Judge delivery using reasoning model (gemini-flash-latest)."""
    # Index guidance items with G1, G2, ...
    indexed_g: list[dict[str, Any]] = []
    for idx, g in enumerate(guidance_items, start=1):
        g_copy = dict(g)
        g_copy["id"] = f"G{idx}"
        indexed_g.append(g_copy)

    # Index reported items with R1, R2, ...
    indexed_r: list[dict[str, Any]] = []
    for idx, r in enumerate(reported_items, start=1):
        r_copy = dict(r)
        r_copy["id"] = f"R{idx}"
        indexed_r.append(r_copy)

    # Format inputs for prompt
    g_text_list = []
    for g in indexed_g:
        target_str = str(g.get("target") or "")
        g_text_list.append(
            f"[{g['id']}] Metric: {g.get('metric')}; Period target applies to: {g.get('applies_to')}; "
            f"Made in: {g.get('period_made')}; Statement: {g.get('statement')}; Target: {target_str}; "
            f"Firmness: {g.get('firmness')}; Quote: \"{g.get('quote')}\""
        )
    guidance_text = "\n".join(g_text_list) if g_text_list else "None"

    timeline_text_list = [entry["evolution"] for entry in timeline_entries]
    timeline_text = "\n".join(timeline_text_list) if timeline_text_list else "None"

    r_text_list = []
    for r in indexed_r:
        r_text_list.append(
            f"[{r['id']}] Metric: {r.get('metric')}; Value: {r.get('value')} {r.get('unit', '')}; "
            f"Period: {r.get('period')}; Reported in: {r.get('period_reported')}; Quote: \"{r.get('quote')}\""
        )
    reported_text = "\n".join(r_text_list) if r_text_list else "None"

    n_text_list = [f"[{n['id']}] {n['description']}" for n in n_items]
    financials_text = "\n".join(n_text_list) if n_text_list else "None"

    template = load_verdicts_prompt_template()
    prompt = (
        template.replace("{ticker}", ticker)
        .replace("{guidance_items}", guidance_text)
        .replace("{guidance_timeline}", timeline_text)
        .replace("{reported_figures}", reported_text)
        .replace("{financial_results}", financials_text)
    )

    # Call LLM reasoning model
    response = call_json(
        task="reasoning",
        prompt=prompt,
        prompt_version="verdicts_v1",
        use_cache=True,
    )

    if not isinstance(response, dict):
        logger.warning("Unexpected non-dict response from reasoning model: %s", response)
        response = {"verdicts": [], "read": ""}

    raw_verdicts = response.get("verdicts", [])
    read = response.get("read", "")

    # Valid ID set for evidence checking
    valid_ids = {g["id"] for g in indexed_g} | {r["id"] for r in indexed_r} | {n["id"] for n in n_items}
    g_by_id = {g["id"]: g for g in indexed_g}
    r_by_id = {r["id"]: r for r in indexed_r}

    validated_verdicts = []
    cited_sources = []

    for v in raw_verdicts:
        v_copy = dict(v)
        ev_ids = v_copy.get("evidence_ids") or []
        # Validate that every evidence id exists
        all_valid = all(eid in valid_ids for eid in ev_ids)
        if not all_valid or not ev_ids:
            if not all_valid:
                v_copy["verdict"] = "unverifiable"
                v_copy["evidence"] = (v_copy.get("evidence", "") + " [unreferenced evidence ID]").strip()

        # Attach cited guidance and reported sources
        g_id = v_copy.get("id")
        if g_id in g_by_id:
            src = g_by_id[g_id]
            cited_sources.append({
                "id": g_id,
                "kind": "guidance",
                "document_id": src.get("document_id"),
                "period": src.get("period_made"),
                "quote": src.get("quote"),
                "speaker": src.get("speaker"),
                "page": src.get("page"),
            })

        for eid in ev_ids:
            if eid in r_by_id:
                r_src = r_by_id[eid]
                cited_sources.append({
                    "id": eid,
                    "kind": "reported",
                    "document_id": r_src.get("document_id"),
                    "period": r_src.get("period_reported"),
                    "quote": r_src.get("quote"),
                    "page": r_src.get("page"),
                })

        validated_verdicts.append(v_copy)

    # Compute verdict counts in Python
    counts_dict: dict[str, int] = {
        "delivered": 0,
        "missed": 0,
        "partly": 0,
        "on_track": 0,
        "behind": 0,
        "revised_down": 0,
        "revised_up": 0,
        "unverifiable": 0,
    }

    for v in validated_verdicts:
        v_name = v.get("verdict", "unverifiable")
        if v_name in counts_dict:
            counts_dict[v_name] += 1
        else:
            counts_dict["unverifiable"] += 1

    total_promises = len(validated_verdicts)
    counts_parts = [f"{total_promises} promises"]
    if counts_dict["delivered"]:
        counts_parts.append(f"{counts_dict['delivered']} delivered")
    if counts_dict["missed"]:
        counts_parts.append(f"{counts_dict['missed']} missed")
    if counts_dict["partly"]:
        counts_parts.append(f"{counts_dict['partly']} partly")
    if counts_dict["on_track"]:
        counts_parts.append(f"{counts_dict['on_track']} on track")
    if counts_dict["behind"]:
        counts_parts.append(f"{counts_dict['behind']} behind")
    if counts_dict["revised_down"]:
        counts_parts.append(f"{counts_dict['revised_down']} revised down")
    if counts_dict["revised_up"]:
        counts_parts.append(f"{counts_dict['revised_up']} revised up")
    if counts_dict["unverifiable"]:
        counts_parts.append(f"{counts_dict['unverifiable']} unverifiable")

    counts_line = " · ".join(counts_parts)

    result_payload = {
        "verdicts": validated_verdicts,
        "read": read,
        "counts": counts_line,
        "counts_breakdown": counts_dict,
        "total_promises": total_promises,
    }
    return result_payload, cited_sources


def run_promises_for_ticker(ticker: str) -> dict[str, Any]:
    """Execute full 3-step promises pipeline for a ticker."""
    ticker = ticker.strip().upper()
    logger.info("Running promises evaluation for %s", ticker)

    # 1. Fetch transcripts from documents table
    client = get_client()
    res = client.table("documents").select("*").eq("ticker", ticker).eq("kind", "transcript").order("event_date", desc=True).execute()
    transcripts = res.data or []
    if not transcripts:
        raise ValueError(f"No transcripts found for ticker {ticker}. Run research/build_corpus.py first.")

    # 2. Fetch financials table for N-numbers
    f_res = client.table("financials").select("*").eq("ticker", ticker).execute()
    financials_row = f_res.data[0] if f_res.data else {}

    # Step 1 & 2: Extract & Verify per transcript
    all_verified_guidance = []
    all_verified_reported = []
    total_quotes_extracted = 0
    total_quotes_verified = 0

    for doc in transcripts:
        period = doc.get("period", "")
        raw_claims = extract_claims_from_transcript(doc)
        v_guidance, v_reported, extracted_cnt, verified_cnt = verify_extracted_claims(doc, raw_claims)
        total_quotes_extracted += extracted_cnt
        total_quotes_verified += verified_cnt
        all_verified_guidance.extend(v_guidance)
        all_verified_reported.extend(v_reported)
        logger.info(
            "%s %s: extracted %d quotes, verified %d (%.0f%%)",
            ticker,
            period,
            extracted_cnt,
            verified_cnt,
            (verified_cnt / extracted_cnt * 100.0) if extracted_cnt else 0,
        )

    # Build guidance timeline
    timeline_entries = build_guidance_timeline(all_verified_guidance)

    # Compute financial growth rates (N numbers)
    n_items = compute_quarterly_financial_numbers(financials_row)

    # Step 3: Judge with reasoning model
    judgement, cited_sources = judge_promises_for_company(
        ticker=ticker,
        guidance_items=all_verified_guidance,
        timeline_entries=timeline_entries,
        reported_items=all_verified_reported,
        n_items=n_items,
    )

    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reasoning_model = MODEL_IDS.get("reasoning", "gemini-flash-latest")

    # Save to research table: section 'promises'
    upsert("research", {
        "ticker": ticker,
        "section": "promises",
        "content": judgement,
        "sources": cited_sources,
        "model": reasoning_model,
        "generated_at": now_utc,
    }, on_conflict="ticker,section")

    # Save to research table: section 'guidance_timeline'
    timeline_sources = [
        {
            "metric": t["metric"],
            "applies_to": t["applies_to"],
            "quotes": [it.get("quote") for it in t.get("items", [])],
        }
        for t in timeline_entries
    ]
    upsert("research", {
        "ticker": ticker,
        "section": "guidance_timeline",
        "content": {"timeline": [t["evolution"] for t in timeline_entries]},
        "sources": timeline_sources,
        "model": "python",
        "generated_at": now_utc,
    }, on_conflict="ticker,section")

    logger.info("Saved research sections 'promises' and 'guidance_timeline' for %s", ticker)

    return {
        "ticker": ticker,
        "quotes_extracted": total_quotes_extracted,
        "quotes_verified": total_quotes_verified,
        "counts": judgement["counts"],
        "read": judgement["read"],
        "verdicts": judgement["verdicts"],
        "timeline": [t["evolution"] for t in timeline_entries],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate management promises and guidance for an NSE ticker.")
    parser.add_argument("--ticker", required=True, help="NSE ticker symbol (e.g. PERSISTENT, DIXON)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    res = run_promises_for_ticker(args.ticker)
    print("\n" + "=" * 70)
    print(f"PROMISES EVALUATION: {res['ticker']}")
    print("=" * 70)
    print(f"Quotes: {res['quotes_extracted']} extracted, {res['quotes_verified']} verified")
    print(f"Counts: {res['counts']}")
    print(f"Read: {res['read']}")
    print("\nVerdicts:")
    for v in res["verdicts"]:
        print(f"  [{v.get('id')}] {v.get('promise')} ({v.get('made_in')}): {v.get('verdict')}")
        print(f"       Evidence: {v.get('evidence')}")
    print("=" * 70 + "\n")
