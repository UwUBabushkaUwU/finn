"""Extract, verify, and judge management promises from concall transcripts.

FINN Research Engine - Promises & Guidance Tracker (v2).
Three steps:
  1. Extract headline guidance and reported figures using bulk LLM (once per transcript).
  2. Verify all extracted quotes in Python (no LLM), group targets across quarters,
     and deterministically label revisions by comparing midpoints.
  3. Judge delivery using reasoning LLM (once per company), followed by strict
     Python post-checks that override the model on period mismatch, unit mismatch,
     or range violations.
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

# Ensure utf-8 stdout/stderr on Windows to avoid UnicodeEncodeError for ₹
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

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
    text = re.sub(r"[\u2018\u2019\u201a\u201b\u2032']", "'", text)
    text = re.sub(r'[\u201c\u201d\u201e\u201f\u2033"]', '"', text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def parse_page_number(page_val: Any) -> int:
    """Robustly parse page number from int, string ('p.4', '4', '[p.4]')."""
    if isinstance(page_val, int):
        return max(1, page_val)
    if isinstance(page_val, str):
        digits = "".join(c for c in page_val if c.isdigit())
        if digits:
            return max(1, int(digits))
    return 1


def normalize_unit(unit_str: str | None, hint: str = "") -> str | None:
    """Normalize unit representation to standard categories: %, ₹ cr, $, units."""
    # First check unit_str directly if provided
    if unit_str:
        u = unit_str.strip().lower()
        if any(k in u for k in ["$", "usd", "dollar"]):
            return "$"
        if any(k in u for k in ["%", "percent", "pct", "bps"]):
            return "%"
        if "₹" in u or re.search(r"\b(?:rs|inr|cr|crore|crores|lakh|lakhs)\b", u):
            return "₹ cr"
        if re.search(r"\b(?:unit|units|volume|volumes|million|millions|mn|store|stores|nos|ton|tons|capacity|mw|gw|sqft)\b", u):
            return "units"

    # Next check text hint using regex whole words
    s = hint.lower()
    if any(k in s for k in ["$", "usd", "dollar"]):
        return "$"
    if any(k in s for k in ["%", "percent", "pct", "bps", "margin"]):
        return "%"
    if "₹" in s or re.search(r"\b(?:rs|inr|cr|crore|crores|lakh|lakhs)\b", s):
        return "₹ cr"
    if re.search(r"\b(?:unit|units|volume|volumes|million|millions|mn|store|stores|nos|ton|tons|capacity|mw|gw|sqft)\b", s):
        return "units"
    return None


def normalize_period(p: str | None) -> str:
    """Normalize fiscal period string (e.g. 'FY26', 'Q2 FY27' -> 'FY26', 'Q2FY27')."""
    return re.sub(r"[^A-Za-z0-9]", "", str(p or "")).upper()


def verify_quote_on_pages(quote: str, pages: list[str], page_num: int) -> bool:
    """Verify that quote appears on the specified page of the transcript.
    
    Checks exact substring match or sliding window difflib match >= 90%.
    Also checks nearby pages (page_num - 1, page_num - 2, page_num, etc.) to handle 1-off indexing.
    """
    if not quote or not pages:
        return False

    norm_quote = normalize_text(quote)
    if not norm_quote:
        return False

    candidate_indices = [page_num - 1, page_num - 2, page_num, page_num - 3, page_num + 1]
    q_len = len(norm_quote)

    for idx in candidate_indices:
        if 0 <= idx < len(pages):
            page_text = normalize_text(pages[idx])
            if norm_quote in page_text:
                return True

            step = max(1, q_len // 3)
            for i in range(0, max(1, len(page_text) - q_len + 1), step):
                window = page_text[i : i + q_len + 20]
                ratio = difflib.SequenceMatcher(None, norm_quote, window).ratio()
                if ratio >= 0.90:
                    return True

    return False


def load_claims_prompt_template() -> str:
    """Load claims extraction prompt from research/prompts/claims_v2.txt."""
    path = PROJECT_ROOT / "research" / "prompts" / "claims_v2.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_verdicts_prompt_template() -> str:
    """Load verdicts evaluation prompt from research/prompts/verdicts_v2.txt."""
    path = PROJECT_ROOT / "research" / "prompts" / "verdicts_v2.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def format_transcript_with_page_markers(pages: list[str]) -> str:
    """Format transcript pages with [p.1], [p.2], ... markers."""
    chunks = []
    for i, p_text in enumerate(pages, start=1):
        chunks.append(f"[p.{i}]\n{p_text.strip()}")
    return "\n\n".join(chunks)


def extract_claims_from_transcript(doc: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Extract headline guidance and reported figures using bulk task."""
    period = doc.get("period", "Unknown")
    pages = doc.get("pages") or []
    text_ok = doc.get("text_ok", True)
    template = load_claims_prompt_template()

    pdf_bytes: bytes | None = None
    if text_ok and pages:
        transcript_text = format_transcript_with_page_markers(pages)
        prompt = template.replace("{period}", period).replace("{transcript_text}", transcript_text)
    else:
        logger.info("Transcript text_ok=False for %s; fetching raw PDF", period)
        url = doc["url"]
        resp = requests.get(url, timeout=30)
        pdf_bytes = resp.content
        prompt = template.replace("{period}", period).replace("{transcript_text}", "[Attached PDF Document]")

    response = call_json(
        task="bulk",
        prompt=prompt,
        prompt_version="claims_v2",
        pdf_bytes=pdf_bytes,
        use_cache=True,
    )

    if not isinstance(response, dict):
        logger.warning("Unexpected non-dict response from LLM: %s", response)
        return {"guidance": [], "reported": []}

    guidance = response.get("guidance", [])
    reported = response.get("reported", [])

    # Normalize covers on reported figures
    clean_reported = []
    if isinstance(reported, list):
        for r in reported:
            if isinstance(r, dict):
                r_copy = dict(r)
                if "covers" not in r_copy or not r_copy["covers"]:
                    r_copy["covers"] = r_copy.get("period", period)
                clean_reported.append(r_copy)

    return {
        "guidance": guidance if isinstance(guidance, list) else [],
        "reported": clean_reported,
    }


def verify_extracted_claims(
    doc: dict[str, Any], raw_claims: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """Step 2: Verify every quote against transcript pages in Python.
    
    Excludes non-headline business guidance like tax rate / ETR, dividend policy, accounting.
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
        metric = (item.get("metric") or "").strip().lower()
        statement = (item.get("statement") or "").lower()
        
        # Hard Python exclusion for tax rates, dividend policy, accounting
        metric_words = metric.split()
        stmt_words = statement.split()
        if (
            "tax rate" in metric or "tax rate" in statement
            or "etr" in metric_words or "etr" in stmt_words
            or "tax %" in metric or "tax %" in statement
            or "effective tax" in metric or "effective tax" in statement
            or "dividend" in metric or "dividend" in statement
            or "accounting" in metric or "accounting" in statement
        ):
            logger.info("Filtered out non-headline guidance item: %s (%s)", metric, statement[:40])
            continue

        quote = item.get("quote", "")
        page = parse_page_number(item.get("page", 1))

        if verify_quote_on_pages(quote, pages, page):
            item_copy = dict(item)
            item_copy["document_id"] = doc_id
            item_copy["period_made"] = period
            item_copy["event_date"] = event_date
            item_copy["page"] = page
            verified_guidance.append(item_copy)
        else:
            logger.info("Dropped unverified guidance quote on %s [p.%d]: %s", period, page, quote[:60])

    for item in raw_reported:
        quote = item.get("quote", "")
        page = parse_page_number(item.get("page", 1))

        if verify_quote_on_pages(quote, pages, page):
            item_copy = dict(item)
            item_copy["document_id"] = doc_id
            item_copy["period_reported"] = period
            item_copy["event_date"] = event_date
            item_copy["page"] = page
            verified_reported.append(item_copy)
        else:
            logger.info("Dropped unverified reported quote on %s [p.%d]: %s", period, page, quote[:60])

    total_verified = len(verified_guidance) + len(verified_reported)
    return verified_guidance, verified_reported, total_extracted, total_verified


def get_target_midpoint(target: dict[str, Any] | None) -> float | None:
    """Compute numeric midpoint of a target value or range."""
    if not target or not isinstance(target, dict):
        return None
    val = target.get("value")
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    low = target.get("low")
    high = target.get("high")
    if low is not None and high is not None:
        try:
            return (float(low) + float(high)) / 2.0
        except (ValueError, TypeError):
            pass
    if low is not None:
        try:
            return float(low)
        except (ValueError, TypeError):
            pass
    if high is not None:
        try:
            return float(high)
        except (ValueError, TypeError):
            pass
    return None


def normalize_metric(metric: str) -> str:
    """Normalize metric name for reliable grouping across quarters."""
    m = (metric or "").strip().lower()
    if "margin" in m:
        if "gross" in m:
            return "gross margin"
        if "pat" in m or "net" in m:
            return "pat margin"
        return "ebitda margin"
    if "revenue" in m or "sales" in m or "topline" in m or "exports" in m:
        if "growth" in m:
            return "revenue growth"
        if "export" in m:
            return "export revenue"
        return "revenue"
    if "volume" in m:
        if "mobile" in m or "smartphone" in m:
            return "smartphone volume"
        if "refrigerator" in m or "fridge" in m:
            return "refrigerator volume"
        return "volume"
    if "capex" in m:
        return "capex"
    if "aum" in m:
        if "growth" in m:
            return "aum growth"
        return "aum"
    if "credit cost" in m:
        return "credit cost"
    if "nim" in m:
        return "nim"
    if "order book" in m or "inflow" in m:
        return "order book"
    return m


def normalize_applies_to(applies_to_str: str) -> str:
    """Normalize applies_to period (e.g. 'March 2027', 'end of FY27' -> 'FY27')."""
    s = (applies_to_str or "").strip()
    s_lower = s.lower()
    match_fy = re.search(r"fy\s*(\d{2,4})", s_lower)
    if match_fy:
        yr = match_fy.group(1)
        return f"FY{yr[-2:]}"
    match_m = re.search(r"mar(?:ch)?\s*(\d{4})", s_lower)
    if match_m:
        yr = int(match_m.group(1))
        return f"FY{str(yr)[-2:]}"
    match_q = re.search(r"q([1-4])\s*(?:of\s*)?(?:fy)?\s*(\d{2,4})?", s_lower)
    if match_q:
        q_num = match_q.group(1)
        yr_part = match_q.group(2)
        if yr_part:
            return f"Q{q_num} FY{yr_part[-2:]}"
        return f"Q{q_num}"
    return s


def group_targets_and_build_timeline(
    guidance_items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Group guidance by (metric, applies_to) across quarters.
    
    Computes midpoints and deterministically assigns revision labels:
      - raised / cut / unchanged
      - widened (if range only widened around same midpoint)
      - none (if single statement)
    
    Returns (consolidated_targets, timeline_entries).
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for g in guidance_items:
        raw_metric = g.get("metric", "")
        raw_applies = g.get("applies_to", "")
        metric = normalize_metric(raw_metric)
        applies_to = normalize_applies_to(raw_applies)
        if not metric or not applies_to:
            continue
        key = (metric, applies_to)
        if key not in groups:
            groups[key] = []
        groups[key].append(g)

    consolidated_targets: list[dict[str, Any]] = []
    timeline_entries: list[dict[str, Any]] = []
    target_idx = 1

    # Sort groups deterministically
    sorted_group_keys = sorted(groups.keys(), key=lambda k: (k[0], k[1]))

    for metric, applies_to in sorted_group_keys:
        items = groups[(metric, applies_to)]
        # Sort items by call date / period made
        items_sorted = sorted(items, key=lambda x: str(x.get("event_date") or x.get("period_made") or ""))
        first_item = items_sorted[0]
        latest_item = items_sorted[-1]

        first_target = first_item.get("target") or {}
        latest_target = latest_item.get("target") or {}

        # Determine revision label by comparing midpoints
        revision_label = "none"
        if len(items_sorted) > 1:
            m_first = get_target_midpoint(first_target)
            m_latest = get_target_midpoint(latest_target)

            if m_first is not None and m_latest is not None:
                if m_latest > m_first + 1e-4:
                    revision_label = "raised"
                elif m_latest < m_first - 1e-4:
                    revision_label = "cut"
                else:
                    # Midpoints are equal; check if range only widened
                    f_low, f_high = first_target.get("low"), first_target.get("high")
                    l_low, l_high = latest_target.get("low"), latest_target.get("high")
                    if (f_low is not None and f_high is not None and
                            l_low is not None and l_high is not None):
                        try:
                            f_span = float(f_high) - float(f_low)
                            l_span = float(l_high) - float(l_low)
                            if l_span > f_span + 1e-4:
                                revision_label = "widened"
                            else:
                                revision_label = "unchanged"
                        except (ValueError, TypeError):
                            revision_label = "unchanged"
                    else:
                        revision_label = "unchanged"
            else:
                revision_label = "unchanged"

        # Build evolution history string
        steps = []
        for it in items_sorted:
            t_data = it.get("target") or {}
            val_str = ""
            if t_data.get("value") is not None:
                val_str = f"{t_data['value']}{t_data.get('unit', '')}"
            elif t_data.get("low") is not None and t_data.get("high") is not None:
                val_str = f"{t_data['low']}–{t_data['high']}{t_data.get('unit', '')}"
            elif it.get("statement"):
                val_str = it["statement"]
            else:
                val_str = "target updated"
            steps.append(f"{val_str} ({it.get('period_made', '')})")

        evolution_str = f"{applies_to} {metric}: " + " → ".join(steps)

        # Target unit
        target_unit = (
            latest_target.get("unit")
            or first_target.get("unit")
            or normalize_unit(None, latest_item.get("statement", "") + " " + metric)
            or ""
        )

        t_obj = {
            "id": f"T{target_idx}",
            "metric": metric,
            "applies_to": applies_to,
            "statement": latest_item.get("statement", first_item.get("statement", "")),
            "first_made_in": first_item.get("period_made", ""),
            "latest_period": latest_item.get("period_made", ""),
            "target": latest_target or first_target,
            "earliest_target": first_target,
            "revision_label": revision_label,
            "evolution": evolution_str,
            "unit": target_unit,
            "items": items_sorted,
        }
        consolidated_targets.append(t_obj)

        timeline_entries.append({
            "metric": metric,
            "applies_to": applies_to,
            "evolution": evolution_str,
            "items": items_sorted,
        })
        target_idx += 1

    return consolidated_targets, timeline_entries


def compute_financial_numbers(financials_row: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute financial numbers tagged with explicit covers periods and units.
    
    Extracts:
      - Quarterly P&L rows with QoQ and YoY, covers='Q# FY##'
      - H1 totals and YoY growth, covers='H1 FY##'
      - TTM totals, covers='TTM'
      - Annual P&L rows (last 4 years), covers='FY##'
    """
    tables = financials_row.get("tables", {})
    q_table = tables.get("quarterly_results", {})
    columns = q_table.get("columns", [])
    rows = q_table.get("rows", [])

    n_items: list[dict[str, Any]] = []
    counter = 1

    month_map = {
        "jun": ("Q1", 1),
        "sep": ("Q2", 1),
        "dec": ("Q3", 1),
        "mar": ("Q4", 0),
    }

    q_covers_list = []
    col_labels = []
    for col in columns:
        parts = col.split()
        if len(parts) >= 2 and parts[1].isdigit():
            m_prefix = parts[0][:3].lower()
            year_int = int(parts[1])
            if m_prefix in month_map:
                q_name, add_year = month_map[m_prefix]
                fy_code = f"FY{str(year_int + add_year)[-2:]}"
                q_cov = f"{q_name} {fy_code}"
                q_covers_list.append(q_cov)
                col_labels.append(f"{q_cov} ({col})")
            else:
                q_covers_list.append(col)
                col_labels.append(col)
        else:
            q_covers_list.append(col)
            col_labels.append(col)

    # 1. Quarterly Results Rows
    num_cols = len(columns)
    for row in rows:
        label = row.get("label", "")
        values = row.get("values", [])
        is_pct = "%" in label or "margin" in label.lower() or "growth" in label.lower()
        row_unit = "%" if is_pct else "₹ cr"

        for i in range(num_cols):
            v_curr = values[i] if i < len(values) else None
            if v_curr is None:
                continue

            q_cov = q_covers_list[i]
            parts = [f"{label} {col_labels[i]} = {v_curr:,.1f}{row_unit}"]

            if i > 0:
                v_prev = values[i - 1] if (i - 1) < len(values) else None
                if v_prev is not None and v_prev != 0:
                    qoq = ((v_curr - v_prev) / abs(v_prev)) * 100.0
                    parts.append(f"{qoq:+.1f}% QoQ vs {q_covers_list[i - 1]}")

            if i >= 4:
                v_yoy = values[i - 4] if (i - 4) < len(values) else None
                if v_yoy is not None and v_yoy != 0:
                    yoy = ((v_curr - v_yoy) / abs(v_yoy)) * 100.0
                    parts.append(f"{yoy:+.1f}% YoY vs {q_covers_list[i - 4]}")

            n_items.append({
                "id": f"N{counter}",
                "label": label,
                "covers": q_cov,
                "value": v_curr,
                "unit": row_unit,
                "description": "; ".join(parts),
            })
            counter += 1

        # Trailing 4 Quarters (TTM)
        if num_cols >= 8:
            last_4 = [values[j] for j in range(num_cols - 4, num_cols) if j < len(values) and values[j] is not None]
            prev_4 = [values[j] for j in range(num_cols - 8, num_cols - 4) if j < len(values) and values[j] is not None]
            if len(last_4) == 4 and len(prev_4) == 4:
                sum_last = sum(last_4)
                sum_prev = sum(prev_4)
                if sum_prev != 0:
                    pct = ((sum_last - sum_prev) / abs(sum_prev)) * 100.0
                    ttm_desc = (
                        f"{label} Trailing 4 Quarters ({q_covers_list[num_cols-4]} to {q_covers_list[num_cols-1]}) "
                        f"= {sum_last:,.1f}{row_unit} vs prev 4Q {sum_prev:,.1f} ({pct:+.1f}% YoY)"
                    )
                    n_items.append({
                        "id": f"N{counter}",
                        "label": label,
                        "covers": "TTM",
                        "value": sum_last,
                        "unit": row_unit,
                        "description": ttm_desc,
                    })
                    counter += 1

    # 2. Compute H1 numbers if both Q1 and Q2 exist
    for row in rows:
        label = row.get("label", "")
        values = row.get("values", [])
        is_pct = "%" in label or "margin" in label.lower()
        if is_pct:
            continue

        for i in range(1, num_cols):
            cov_curr = q_covers_list[i]
            cov_prev = q_covers_list[i - 1]
            if cov_curr.startswith("Q2 ") and cov_prev.startswith("Q1 "):
                fy_curr = cov_curr.split()[1]
                fy_prev = cov_prev.split()[1]
                if fy_curr == fy_prev:
                    v_q2 = values[i] if i < len(values) else None
                    v_q1 = values[i - 1] if (i - 1) < len(values) else None
                    if v_q1 is not None and v_q2 is not None:
                        h1_val = v_q1 + v_q2
                        h1_cov = f"H1 {fy_curr}"
                        n_items.append({
                            "id": f"N{counter}",
                            "label": label,
                            "covers": h1_cov,
                            "value": h1_val,
                            "unit": "₹ cr",
                            "description": f"{label} {h1_cov} = {h1_val:,.1f} ₹ cr (sum of Q1 and Q2)",
                        })
                        counter += 1

    # 3. Annual Profit & Loss (recent 4 years only to keep prompt concise)
    pl_table = tables.get("profit_loss", {})
    pl_columns = pl_table.get("columns", [])
    pl_rows = pl_table.get("rows", [])

    recent_pl_indices = [idx for idx in range(max(0, len(pl_columns) - 4), len(pl_columns))]

    for row in pl_rows:
        label = row.get("label", "")
        values = row.get("values", [])
        is_pct = "%" in label or "margin" in label.lower()
        row_unit = "%" if is_pct else "₹ cr"

        for idx in recent_pl_indices:
            if idx >= len(values) or values[idx] is None:
                continue
            val = values[idx]
            col = pl_columns[idx]
            match = re.search(r"Mar\s+(\d{4})", col)
            if match:
                yr = match.group(1)
                fy_cov = f"FY{yr[-2:]}"
                desc = f"{label} {fy_cov} (Annual Mar {yr}) = {val:,.1f}{row_unit}"
                n_items.append({
                    "id": f"N{counter}",
                    "label": label,
                    "covers": fy_cov,
                    "value": val,
                    "unit": row_unit,
                    "description": desc,
                })
                counter += 1

    return n_items


def apply_python_overrides(
    raw_verdicts: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    r_items: list[dict[str, Any]],
    n_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Execute deterministic Python post-checks that override the judge model:
    
    1. Missing T ids from judge output become 'not_judged'.
    2. Invalid evidence IDs overridden to 'unverifiable'.
    3. Evidence must match target unit (%, ₹ cr, $, units); else 'unverifiable'.
    4. delivered / missed / partly require evidence whose covers equals applies_to;
       otherwise downgraded (delivered -> on_track, missed/partly -> behind) with 'partial period'.
    5. Numeric targets with range: if evidence < low, cannot be on_track or delivered (behind/missed);
       if > high, cannot be behind or missed.
    6. Log and count every override.
    """
    t_by_id = {t["id"]: t for t in targets}
    r_by_id = {r["id"]: r for r in r_items}
    n_by_id = {n["id"]: n for n in n_items}
    valid_ev_ids = set(r_by_id.keys()) | set(n_by_id.keys())

    overrides_count = 0
    final_verdicts: list[dict[str, Any]] = []

    # Map raw model verdicts by target id
    model_v_by_id: dict[str, dict[str, Any]] = {}
    for v in raw_verdicts:
        if isinstance(v, dict) and "id" in v:
            model_v_by_id[v["id"]] = v

    # Check every target deterministically
    for t in targets:
        t_id = t["id"]
        metric = t.get("metric", "")
        applies_to = t.get("applies_to", "")
        applies_to_norm = normalize_period(applies_to)
        statement = t.get("statement", "")
        revision_label = t.get("revision_label", "none")

        if t_id not in model_v_by_id:
            logger.warning("Override [%s]: missing in judge output -> not_judged", t_id)
            overrides_count += 1
            final_verdicts.append({
                "id": t_id,
                "promise": statement,
                "made_in": t.get("first_made_in", ""),
                "applies_to": applies_to,
                "verdict": "not_judged",
                "evidence": "Not judged by model",
                "evidence_ids": [],
                "revision_label": revision_label,
            })
            continue

        raw_v = model_v_by_id[t_id]
        verdict = (raw_v.get("verdict") or "unverifiable").strip().lower()
        evidence_text = (raw_v.get("evidence") or "").strip()
        ev_ids = raw_v.get("evidence_ids") or []
        if isinstance(ev_ids, str):
            ev_ids = [ev_ids]

        # 1. Validate Evidence IDs
        valid_cites = [eid for eid in ev_ids if eid in valid_ev_ids]
        if not valid_cites and verdict != "unverifiable":
            logger.warning("Override [%s]: %s -> unverifiable (no valid evidence IDs)", t_id, verdict)
            verdict = "unverifiable"
            evidence_text += " [Override: unreferenced evidence ID]"
            overrides_count += 1
            ev_ids = []
        else:
            ev_ids = valid_cites

        cited_items = []
        for eid in ev_ids:
            if eid in r_by_id:
                cited_items.append(r_by_id[eid])
            elif eid in n_by_id:
                cited_items.append(n_by_id[eid])

        # 2. Unit Matching Check
        target_unit = t.get("unit") or (t.get("target") or {}).get("unit")
        t_unit_norm = normalize_unit(target_unit, statement + " " + metric)

        if t_unit_norm is not None and cited_items:
            has_matching_unit = any(
                normalize_unit(e.get("unit"), e.get("description", "") or e.get("quote", "")) == t_unit_norm
                for e in cited_items
            )
            if not has_matching_unit and verdict != "unverifiable":
                orig_v = verdict
                verdict = "unverifiable"
                evidence_text += f" [Override: evidence unit mismatch vs guided {t_unit_norm}]"
                overrides_count += 1
                logger.warning(
                    "Override [%s]: %s -> unverifiable (unit mismatch: guided %s)",
                    t_id,
                    orig_v,
                    t_unit_norm,
                )

        # 3. Period Completeness Check (delivered / missed / partly require exact covers == applies_to)
        if verdict in ["delivered", "missed", "partly"]:
            has_matching_covers = False
            for e in cited_items:
                c_norm = normalize_period(e.get("covers"))
                if c_norm and c_norm == applies_to_norm:
                    has_matching_covers = True
                    break

            if not has_matching_covers:
                orig_v = verdict
                if verdict == "delivered":
                    verdict = "on_track"
                else:
                    verdict = "behind"
                evidence_text += " (partial period)"
                overrides_count += 1
                logger.warning(
                    "Override [%s]: %s -> %s (partial period: guided %s vs evidence %s)",
                    t_id,
                    orig_v,
                    verdict,
                    applies_to,
                    [e.get("covers") for e in cited_items],
                )

        # 4. Numeric Range Sanity Check
        t_target = t.get("target") or {}
        low = t_target.get("low")
        high = t_target.get("high")
        if low is not None and high is not None:
            try:
                low_f = float(low)
                high_f = float(high)

                matching_vals = []
                for e in cited_items:
                    e_val = e.get("value")
                    if e_val is not None:
                        try:
                            val_f = float(e_val)
                            e_unit_norm = normalize_unit(e.get("unit"), e.get("description", "") or e.get("quote", ""))
                            if e_unit_norm == t_unit_norm:
                                matching_vals.append((val_f, e.get("covers", "")))
                        except (ValueError, TypeError):
                            pass

                if matching_vals:
                    for val_f, cov in matching_vals:
                        cov_norm = normalize_period(cov)
                        period_ended = (cov_norm == applies_to_norm)

                        if val_f < low_f:
                            if verdict in ["on_track", "delivered"]:
                                orig_v = verdict
                                verdict = "missed" if period_ended else "behind"
                                evidence_text += f" [Override: evidence {val_f} below guided low {low_f}]"
                                overrides_count += 1
                                logger.warning(
                                    "Override [%s]: %s -> %s (value %s < low %s)",
                                    t_id,
                                    orig_v,
                                    verdict,
                                    val_f,
                                    low_f,
                                )
                                break
                        elif val_f > high_f:
                            if verdict in ["behind", "missed"]:
                                orig_v = verdict
                                verdict = "delivered" if period_ended else "on_track"
                                evidence_text += f" [Override: evidence {val_f} above guided high {high_f}]"
                                overrides_count += 1
                                logger.warning(
                                    "Override [%s]: %s -> %s (value %s > high %s)",
                                    t_id,
                                    orig_v,
                                    verdict,
                                    val_f,
                                    high_f,
                                )
                                break
            except (ValueError, TypeError):
                pass

        final_verdicts.append({
            "id": t_id,
            "promise": statement,
            "made_in": t.get("first_made_in", ""),
            "applies_to": applies_to,
            "verdict": verdict,
            "evidence": evidence_text.strip(),
            "evidence_ids": ev_ids,
            "revision_label": revision_label,
        })

    def get_t_index(item: dict[str, Any]) -> int:
        num = "".join(c for c in item.get("id", "") if c.isdigit())
        return int(num) if num else 999

    final_verdicts.sort(key=get_t_index)
    return final_verdicts, overrides_count


def judge_promises_for_company(
    ticker: str,
    targets: list[dict[str, Any]],
    timeline_entries: list[dict[str, Any]],
    reported_items: list[dict[str, Any]],
    n_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Step 3: Judge delivery using reasoning model and apply Python post-checks."""
    indexed_r: list[dict[str, Any]] = []
    for idx, r in enumerate(reported_items, start=1):
        r_copy = dict(r)
        r_copy["id"] = f"R{idx}"
        indexed_r.append(r_copy)

    # Format targets for prompt
    t_text_list = []
    for t in targets:
        t_text_list.append(
            f"[{t['id']}] Metric: {t.get('metric')}; Applies to: {t.get('applies_to')}; "
            f"First made: {t.get('first_made_in')}; Latest status: {t.get('latest_period')}; "
            f"Revision: {t.get('revision_label')}; Statement: \"{t.get('statement')}\"; "
            f"Target: {str(t.get('target'))}; Unit: {t.get('unit')}; Evolution: \"{t.get('evolution')}\""
        )
    targets_text = "\n".join(t_text_list) if t_text_list else "None"

    # Format reported items for prompt
    r_text_list = []
    for r in indexed_r:
        r_text_list.append(
            f"[{r['id']}] Metric: {r.get('metric')}; Value: {r.get('value')} {r.get('unit', '')}; "
            f"Covers: {r.get('covers')}; Reported in: {r.get('period_reported')}; Quote: \"{r.get('quote')}\""
        )
    reported_text = "\n".join(r_text_list) if r_text_list else "None"

    # Format financial numbers for prompt
    n_text_list = [f"[{n['id']}] {n['description']}; Covers: {n.get('covers')}; Unit: {n.get('unit')}" for n in n_items]
    financials_text = "\n".join(n_text_list) if n_text_list else "None"

    template = load_verdicts_prompt_template()
    prompt = (
        template.replace("{ticker}", ticker)
        .replace("{targets}", targets_text)
        .replace("{reported_figures}", reported_text)
        .replace("{financial_results}", financials_text)
    )

    response = call_json(
        task="reasoning",
        prompt=prompt,
        prompt_version="verdicts_v2",
        use_cache=True,
    )

    if not isinstance(response, dict):
        logger.warning("Unexpected non-dict response from reasoning model: %s", response)
        response = {"verdicts": [], "read": ""}

    raw_verdicts = response.get("verdicts", [])
    read = response.get("read", "")

    # Execute deterministic Python post-checks and overrides
    validated_verdicts, overrides_count = apply_python_overrides(
        raw_verdicts=raw_verdicts,
        targets=targets,
        r_items=indexed_r,
        n_items=n_items,
    )

    # Gather cited sources for web UI
    t_by_id = {t["id"]: t for t in targets}
    r_by_id = {r["id"]: r for r in indexed_r}
    cited_sources = []

    for v in validated_verdicts:
        t_id = v.get("id")
        if t_id in t_by_id:
            t_obj = t_by_id[t_id]
            for it in t_obj.get("items", []):
                cited_sources.append({
                    "id": t_id,
                    "kind": "guidance",
                    "document_id": it.get("document_id"),
                    "period": it.get("period_made"),
                    "quote": it.get("quote"),
                    "speaker": it.get("speaker"),
                    "page": it.get("page"),
                })
        for eid in v.get("evidence_ids", []):
            if eid in r_by_id:
                r_src = r_by_id[eid]
                cited_sources.append({
                    "id": eid,
                    "kind": "reported",
                    "document_id": r_src.get("document_id"),
                    "period": r_src.get("period_reported"),
                    "covers": r_src.get("covers"),
                    "quote": r_src.get("quote"),
                    "page": r_src.get("page"),
                })

    # Compute verdict counts in Python
    counts_dict: dict[str, int] = {
        "delivered": 0,
        "missed": 0,
        "partly": 0,
        "on_track": 0,
        "behind": 0,
        "unverifiable": 0,
        "not_judged": 0,
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
    if counts_dict["unverifiable"]:
        counts_parts.append(f"{counts_dict['unverifiable']} unverifiable")
    if counts_dict["not_judged"]:
        counts_parts.append(f"{counts_dict['not_judged']} not judged")

    counts_line = " · ".join(counts_parts)

    # Revision breakdown
    rev_dict: dict[str, int] = {"raised": 0, "cut": 0, "widened": 0, "unchanged": 0}
    for t in targets:
        r_lbl = t.get("revision_label", "none")
        if r_lbl in rev_dict:
            rev_dict[r_lbl] += 1

    result_payload = {
        "verdicts": validated_verdicts,
        "read": read,
        "counts": counts_line,
        "counts_breakdown": counts_dict,
        "revision_breakdown": rev_dict,
        "overrides_count": overrides_count,
        "total_promises": total_promises,
        "targets": [
            {
                "id": t["id"],
                "metric": t["metric"],
                "applies_to": t["applies_to"],
                "statement": t["statement"],
                "revision_label": t["revision_label"],
                "evolution": t["evolution"],
            }
            for t in targets
        ],
    }
    return result_payload, cited_sources


def run_promises_for_ticker(ticker: str) -> dict[str, Any]:
    """Execute full 3-step promises pipeline for a ticker."""
    ticker = ticker.strip().upper()
    logger.info("Running promises evaluation (v2) for %s", ticker)

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

    # Group guidance into targets T1... and build timeline
    targets, timeline_entries = group_targets_and_build_timeline(all_verified_guidance)
    logger.info("%s: grouped %d verified guidance items into %d unique targets", ticker, len(all_verified_guidance), len(targets))

    # Compute financial growth rates & annual numbers (N numbers)
    n_items = compute_financial_numbers(financials_row)
    logger.info("%s: computed %d financial numbers with covers periods", ticker, len(n_items))

    # Step 3: Judge with reasoning model + Python overrides
    judgement, cited_sources = judge_promises_for_company(
        ticker=ticker,
        targets=targets,
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

    logger.info(
        "Saved research sections for %s. Overrides: %d, Counts: %s",
        ticker,
        judgement["overrides_count"],
        judgement["counts"],
    )

    return {
        "ticker": ticker,
        "quotes_extracted": total_quotes_extracted,
        "quotes_verified": total_quotes_verified,
        "unique_targets": len(targets),
        "overrides_count": judgement["overrides_count"],
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
    print(f"PROMISES EVALUATION (v2): {res['ticker']}")
    print("=" * 70)
    print(f"Quotes: {res['quotes_extracted']} extracted, {res['quotes_verified']} verified")
    print(f"Targets: {res['unique_targets']} unique targets")
    print(f"Overrides: {res['overrides_count']}")
    print(f"Counts: {res['counts']}")
    print(f"Read: {res['read']}")
    print("\nVerdicts:")
    for v in res["verdicts"]:
        print(f"  [{v.get('id')}] {v.get('promise')} ({v.get('made_in')}): {v.get('verdict')} [Rev: {v.get('revision_label')}]")
        print(f"       Evidence: {v.get('evidence')} (IDs: {v.get('evidence_ids')})")
    print("=" * 70 + "\n")
