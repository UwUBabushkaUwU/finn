"""Extract, verify, and judge management promises from concall transcripts.

FINN Research Engine - Promises & Guidance Tracker (v3).
Deterministic Python-first architecture:
  1. Extract headline guidance, reported operational figures, and operational events
     using bulk LLM (prompt version claims_v3).
  2. Verify all extracted quotes in Python (no LLM), group targets across quarters by
     (metric, segment, applies_to), and deterministically label revisions.
  3. Pre-filter candidate evidence in Python by (metric, segment). Targets with no
     candidates are auto-resolved with NO LLM call: 'pending' if period has not ended,
     or 'unverifiable' if it has.
  4. Milestones judged against later call events (delivered on time, partly if late,
     revised_down if delayed, unverifiable if deadline passed without update).
  5. Partial-period amounts extrapolated to annualized run-rate (sum * period_len / months)
     for bounds checking. Rates (%) compared directly.
  6. Strict Python post-checks enforce period completeness and unit matching.
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

# Ensure utf-8 stdout/stderr on Windows to avoid UnicodeEncodeError for ₹ and →
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

ALLOWED_METRICS = {
    "revenue",
    "revenue_growth",
    "ebitda_margin",
    "ebit_margin",
    "pat",
    "pat_growth",
    "capex",
    "order_book",
    "volume",
    "capacity",
    "store_count",
    "aum_growth",
    "credit_cost",
    "nim",
    "milestone",
}


def normalize_text(text: str) -> str:
    """Normalize whitespace and quotation characters for reliable matching."""
    if not text:
        return ""
    text = re.sub(r"[\u2018\u2019\u201a\u201b\u2032']", "'", text)
    text = re.sub(r'[\u201c\u201d\u201e\u201f\u2033"]', '"', text)
    text = re.sub(r"[-–—]", " ", text)
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


def normalize_segment(seg: Any) -> str | None:
    """Normalize business segment name or return None if whole company."""
    if not seg:
        return None
    s = str(seg).strip().lower()
    if s in ["null", "none", "overall", "consolidated", "consol", "company", "total", "entire company"]:
        return None
    # Clean common prefixes/suffixes
    s = re.sub(r"\b(?:division|segment|business)\b", "", s).strip()
    return s if s else None


def normalize_metric(metric: str, hint: str = "") -> str:
    """Normalize metric name strictly to one of ALLOWED_METRICS."""
    h = hint.lower()
    if any(k in h for k in ["$ billion", "billion in annual revenue", "billion revenue", "$2 billion", "$5 billion", "$1 billion"]):
        return "revenue"

    m = (metric or "").strip().lower().replace("-", "_").replace(" ", "_")
    if m in ALLOWED_METRICS:
        return m

    # Heuristic mapping for near matches
    if "ebitda" in m or "opm" in m or "operating_margin" in m:
        return "ebitda_margin"
    if "ebit" in m:
        return "ebit_margin"
    if "pat" in m or "net_profit" in m:
        if "growth" in m:
            return "pat_growth"
        return "pat"
    if "margin" in m:
        return "ebitda_margin"
    if "revenue" in m or "sales" in m or "topline" in m or "turnover" in m:
        if "growth" in m:
            return "revenue_growth"
        return "revenue"
    if "volume" in m or "units" in m:
        return "volume"
    if "capacity" in m or "utilization" in m:
        return "capacity"
    if "store" in m or "branches" in m:
        return "store_count"
    if "capex" in m:
        return "capex"
    if "order" in m or "inflow" in m:
        return "order_book"
    if "aum" in m:
        return "aum_growth"
    if "credit" in m or "loss" in m:
        return "credit_cost"
    if "nim" in m or "spread" in m:
        return "nim"
    if "milestone" in m or "plant" in m or "launch" in m or "commission" in m or "facility" in m:
        return "milestone"

    return "milestone"


def normalize_unit(unit_str: str | None, hint: str = "") -> str | None:
    """Normalize unit representation to standard categories: %, ₹ cr, $, units, stores."""
    if unit_str:
        u = unit_str.strip().lower()
        if any(k in u for k in ["$", "usd", "dollar"]):
            return "$"
        if any(k in u for k in ["%", "percent", "pct", "bps"]):
            return "%"
        if "₹" in u or re.search(r"\b(?:rs|inr|cr|crore|crores|lakh|lakhs)\b", u):
            return "₹ cr"
        if re.search(r"\b(?:store|stores|branches|outlets)\b", u):
            return "stores"
        if re.search(r"\b(?:unit|units|volume|volumes|million|millions|mn|nos|ton|tons|capacity|mw|gw|sqft)\b", u):
            return "units"

    s = hint.lower()
    if any(k in s for k in ["$", "usd", "dollar"]):
        return "$"
    if any(k in s for k in ["%", "percent", "pct", "bps", "margin"]):
        return "%"
    if "₹" in s or re.search(r"\b(?:rs|inr|cr|crore|crores|lakh|lakhs)\b", s):
        return "₹ cr"
    if re.search(r"\b(?:store|stores|branches|outlets)\b", s):
        return "stores"
    if re.search(r"\b(?:unit|units|volume|volumes|million|millions|mn|nos|ton|tons|capacity|mw|gw|sqft)\b", s):
        return "units"
    return None


def normalize_period(p: str | None) -> str:
    """Normalize fiscal period string (e.g. 'FY26', 'Q2 FY27' -> 'FY26', 'Q2FY27')."""
    return re.sub(r"[^A-Za-z0-9]", "", str(p or "")).upper()


def normalize_applies_to(applies_to_str: str) -> str:
    """Normalize applies_to period to absolute fiscal periods."""
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
    match_h = re.search(r"h([1-2])\s*(?:of\s*)?(?:fy)?\s*(\d{2,4})?", s_lower)
    if match_h:
        h_num = match_h.group(1)
        yr_part = match_h.group(2)
        if yr_part:
            return f"H{h_num} FY{yr_part[-2:]}"
        return f"H{h_num}"
    return s


def parse_fiscal_period(p_str: str) -> tuple[int, int]:
    """Parse period string into (fy_year, quarter_num 1..4) on India's April-March year.
    
    Examples:
      'FY26' -> (2026, 4)
      'FY27' -> (2027, 4)
      'Q1 FY27' -> (2027, 1)
      'Q2 FY27' -> (2027, 2)
      'H1 FY27' -> (2027, 2)
      'H2 FY27' -> (2027, 4)
      '9M FY27' -> (2027, 3)
      'March 2026' -> (2026, 4)
      'December 2025' -> (2026, 3)
      'April 2026' -> (2027, 1)
      'December 2026' -> (2027, 3)
    """
    s = (p_str or "").strip().lower()
    
    # Quarter pattern
    m_q = re.search(r"q([1-4])\s*(?:fy\s*(\d{2,4}))?", s)
    if m_q:
        q_num = int(m_q.group(1))
        yr = int(m_q.group(2)) if m_q.group(2) else 27
        if yr < 100:
            yr += 2000
        return (yr, q_num)
        
    # Half-year pattern
    m_h = re.search(r"h([1-2])\s*(?:fy\s*(\d{2,4}))?", s)
    if m_h:
        h_num = int(m_h.group(1))
        q_num = 2 if h_num == 1 else 4
        yr = int(m_h.group(2)) if m_h.group(2) else 27
        if yr < 100:
            yr += 2000
        return (yr, q_num)

    # 9M pattern
    m_9m = re.search(r"9m\s*(?:fy\s*(\d{2,4}))?", s)
    if m_9m:
        yr = int(m_9m.group(1)) if m_9m.group(1) else 27
        if yr < 100:
            yr += 2000
        return (yr, 3)

    # Full year pattern: FY26, FY27, FY2026
    m_fy = re.search(r"fy\s*(\d{2,4})", s)
    if m_fy:
        yr = int(m_fy.group(1))
        if yr < 100:
            yr += 2000
        return (yr, 4)

    # Calendar month-year patterns
    month_map = {
        "jan": (4, 0), "feb": (4, 0), "mar": (4, 0),
        "apr": (1, 1), "may": (1, 1), "jun": (1, 1),
        "jul": (2, 1), "aug": (2, 1), "sep": (2, 1),
        "oct": (3, 1), "nov": (3, 1), "dec": (3, 1),
    }
    for m_prefix, (q_idx, fy_add) in month_map.items():
        if m_prefix in s:
            m_yr = re.search(r"(\d{4})", s)
            if m_yr:
                cal_yr = int(m_yr.group(1))
                return (cal_yr + fy_add, q_idx)
            m_short_yr = re.search(r"'?(\d{2})\b", s)
            if m_short_yr:
                cal_yr = int(m_short_yr.group(1)) + 2000
                return (cal_yr + fy_add, q_idx)

    return (2099, 4)


def get_period_quarter_range(p_str: str) -> tuple[int, int] | None:
    """Parse period string into (start_q_index, end_q_index) where index = fy * 4 + q."""
    s = (p_str or "").strip().lower()
    if not s:
        return None

    # Multi-year pattern: FY26-FY28, FY26–FY28
    m_my = re.search(r"fy\s*(\d{2,4})\s*[-–]\s*fy?\s*(\d{2,4})", s)
    if m_my:
        y1 = int(m_my.group(1))
        y2 = int(m_my.group(2))
        y1 = y1 + 2000 if y1 < 100 else y1
        y2 = y2 + 2000 if y2 < 100 else y2
        return (y1 * 4 + 1, y2 * 4 + 4)

    # Quarter pattern
    m_q = re.search(r"q([1-4])\s*(?:fy\s*(\d{2,4}))?", s)
    if m_q:
        q = int(m_q.group(1))
        yr = int(m_q.group(2)) if m_q.group(2) else 27
        yr = yr + 2000 if yr < 100 else yr
        idx = yr * 4 + q
        return (idx, idx)

    # Half year pattern
    m_h = re.search(r"h([1-2])\s*(?:fy\s*(\d{2,4}))?", s)
    if m_h:
        h = int(m_h.group(1))
        yr = int(m_h.group(2)) if m_h.group(2) else 27
        yr = yr + 2000 if yr < 100 else yr
        if h == 1:
            return (yr * 4 + 1, yr * 4 + 2)
        else:
            return (yr * 4 + 3, yr * 4 + 4)

    # 9M pattern
    m_9m = re.search(r"9m\s*(?:fy\s*(\d{2,4}))?", s)
    if m_9m:
        yr = int(m_9m.group(1)) if m_9m.group(1) else 27
        yr = yr + 2000 if yr < 100 else yr
        return (yr * 4 + 1, yr * 4 + 3)

    # Full year pattern: FY26, FY27, FY2026
    m_fy = re.search(r"fy\s*(\d{2,4})", s)
    if m_fy:
        yr = int(m_fy.group(1))
        yr = yr + 2000 if yr < 100 else yr
        return (yr * 4 + 1, yr * 4 + 4)

    # Month calendar patterns
    month_map = {
        "jan": (4, 0), "january": (4, 0),
        "feb": (4, 0), "february": (4, 0),
        "mar": (4, 0), "march": (4, 0),
        "apr": (1, 1), "april": (1, 1),
        "may": (1, 1),
        "jun": (1, 1), "june": (1, 1),
        "jul": (2, 1), "july": (2, 1),
        "aug": (2, 1), "august": (2, 1),
        "sep": (2, 1), "sept": (2, 1), "september": (2, 1),
        "oct": (3, 1), "october": (3, 1),
        "nov": (3, 1), "november": (3, 1),
        "dec": (3, 1), "december": (3, 1),
    }
    for m_name, (q_num, yr_offset) in month_map.items():
        if m_name in s:
            yr_match = re.search(r"\b(20\d{2})\b", s)
            if yr_match:
                cal_yr = int(yr_match.group(1))
                fy_yr = cal_yr + yr_offset
                idx = fy_yr * 4 + q_num
                return (idx, idx)

    return None


def period_falls_inside(covers_str: str, applies_to_str: str) -> bool:
    """Check whether evidence covers period falls strictly inside target's applies_to."""
    if not covers_str or not applies_to_str:
        return False
    cov_r = get_period_quarter_range(covers_str)
    app_r = get_period_quarter_range(applies_to_str)
    if not cov_r or not app_r:
        return normalize_period(covers_str) == normalize_period(applies_to_str)
    return cov_r[0] >= app_r[0] and cov_r[1] <= app_r[1]


def format_indian_number(val: Any) -> str:
    """Format number with Indian digit grouping (e.g. 1,600 or 12,34,567)."""
    if val is None:
        return ""
    try:
        val_f = float(str(val).replace(",", "").replace("₹", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return str(val)

    is_negative = val_f < 0
    val_f = abs(val_f)

    if val_f == int(val_f):
        s = str(int(val_f))
        dec = ""
    else:
        s_float = f"{val_f:.1f}"
        parts = s_float.split(".")
        s = parts[0]
        dec = "." + parts[1] if len(parts) > 1 else ""

    if len(s) <= 3:
        res = s
    else:
        last3 = s[-3:]
        remaining = s[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        res = ",".join(groups) + "," + last3

    full = f"-{res}{dec}" if is_negative else f"{res}{dec}"
    return full


def format_money(val: Any, unit: str = "cr") -> str:
    """Format single money value with ₹ placed strictly before the number."""
    formatted = format_indian_number(val)
    if not formatted:
        return ""
    u = f" {unit}".rstrip() if unit else ""
    return f"₹{formatted}{u}"


def format_money_range(low: Any, high: Any, unit: str = "cr") -> str:
    """Format money range with ₹ before the first number and unit at the end."""
    f_low = format_indian_number(low)
    f_high = format_indian_number(high)
    u = f" {unit}".rstrip() if unit else ""
    return f"₹{f_low}–{f_high}{u}"


MILESTONE_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "am", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "shall", "should", "may", "might", "must", "can", "could", "this", "that",
    "these", "those", "it", "its", "we", "our", "us", "they", "their", "them", "he",
    "she", "him", "her", "i", "my", "me", "there", "their", "then", "so", "as", "than",
    "target", "expect", "expected", "plan", "planned", "guidance", "guide", "guided",
    "estimated", "estimate", "around", "nearly", "approximately", "achieve", "reach",
    "deliver", "continue", "start", "complete", "completed", "completion", "milestone",
    "status", "update", "likely", "unlikely", "going", "come", "next", "prior",
    "previous", "current", "overall", "total", "company", "management", "said", "call",
    "quarter", "annual", "report", "results", "growth", "numbers", "work", "focus",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug",
    "sep", "sept", "oct", "nov", "dec", "q1", "q2", "q3", "q4", "h1", "h2", "9m",
    "fy24", "fy25", "fy26", "fy27", "fy28", "fy29", "fy30", "year", "years", "month",
    "months", "crore", "crores", "cr", "inr", "rs", "bse", "nse", "date",
}


def extract_content_words(text: str) -> set[str]:
    """Extract normalized content word stems, dropping stopwords and dates."""
    if not text:
        return set()
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    content_words = set()
    for w in words:
        if w in MILESTONE_STOPWORDS:
            continue
        # Suffix stemming & z/s normalization
        w = w.replace("z", "s")
        if w.endswith("tion"):
            w = w[:-4]
        elif w.endswith("ing") and len(w) > 5:
            w = w[:-3]
        elif w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("ed") and len(w) > 4:
            w = w[:-2]
        elif w.endswith("es") and len(w) > 4:
            w = w[:-2]
        elif w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
            w = w[:-1]
        elif w.endswith("ise"):
            w = w[:-3] + "is"
        if len(w) >= 3 and w not in MILESTONE_STOPWORDS:
            content_words.add(w)
    return content_words


def compute_milestone_overlap(promise_stmt: str, event_what: str) -> float:
    """Compute content-word overlap between promise statement and event what."""
    p_words = extract_content_words(promise_stmt)
    e_words = extract_content_words(event_what)
    if not p_words or not e_words:
        return 0.0
    intersection = p_words & e_words
    union = p_words | e_words
    return len(intersection) / len(union) if union else 0.0


def has_period_ended(applies_to_str: str, latest_quarter_str: str = "Q2 FY27") -> bool:
    """Determine whether applies_to period has concluded relative to latest data."""
    t_fy, t_q = parse_fiscal_period(applies_to_str)
    l_fy, l_q = parse_fiscal_period(latest_quarter_str)
    return (t_fy, t_q) <= (l_fy, l_q)


def get_period_length_and_months_covered(applies_to: str, covers: str) -> tuple[int, int]:
    """Return (target_period_months, evidence_months_covered)."""
    t_lower = applies_to.lower()
    c_lower = covers.lower()

    # Target period length
    if "q" in t_lower:
        t_months = 3
    elif "h1" in t_lower or "h2" in t_lower:
        t_months = 6
    elif "9m" in t_lower:
        t_months = 9
    else:
        # Full year default
        t_months = 12

    # Evidence months covered
    if "q" in c_lower:
        c_months = 3
    elif "h1" in c_lower or "h2" in c_lower:
        c_months = 6
    elif "9m" in c_lower:
        c_months = 9
    elif "fy" in c_lower or "annual" in c_lower or "ttm" in c_lower:
        c_months = 12
    else:
        c_months = 3

    return t_months, min(t_months, c_months)


def verify_quote_on_pages(quote: str, pages: list[str], page_num: int) -> bool:
    """Verify that quote appears on or near the specified page of the transcript."""
    if not quote or not pages:
        return False

    norm_quote = normalize_text(quote)
    if not norm_quote:
        return False

    q_words = norm_quote.split()
    if not q_words:
        return False

    candidate_indices = [page_num - 1, page_num - 2, page_num, page_num - 3, page_num + 1]

    for idx in candidate_indices:
        if 0 <= idx < len(pages):
            p_prev = pages[idx - 1] if idx > 0 else ""
            p_curr = pages[idx]
            p_next = pages[idx + 1] if idx + 1 < len(pages) else ""
            full_window = normalize_text(p_prev + " " + p_curr + " " + p_next)

            # 1. Direct substring
            if norm_quote in full_window:
                return True

            # 2. Check 4-word sub-slices (handles boundary truncation or prefix/suffix slight differences)
            if len(q_words) >= 4:
                prefix = " ".join(q_words[:5])
                suffix = " ".join(q_words[-5:])
                mid = " ".join(q_words[1:6])
                if prefix in full_window or suffix in full_window or mid in full_window:
                    return True

            # 3. Fuzzy search around first 3 words
            if len(q_words) >= 3:
                first3 = " ".join(q_words[:3])
                pos = full_window.find(first3)
                if pos != -1:
                    sub = full_window[pos : pos + len(norm_quote) + 20]
                    if difflib.SequenceMatcher(None, norm_quote, sub).ratio() >= 0.80:
                        return True

    return False


def load_claims_prompt_template() -> str:
    """Load claims extraction prompt from research/prompts/claims_v3.txt."""
    path = PROJECT_ROOT / "research" / "prompts" / "claims_v3.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_verdicts_prompt_template() -> str:
    """Load verdicts evaluation prompt from research/prompts/verdicts_v3.txt."""
    path = PROJECT_ROOT / "research" / "prompts" / "verdicts_v3.txt"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def format_transcript_with_page_markers(pages: list[str]) -> str:
    """Format transcript pages with [p.1], [p.2], ... markers."""
    chunks = []
    for i, p_text in enumerate(pages, start=1):
        chunks.append(f"[p.{i}]\n{p_text.strip()}")
    return "\n\n".join(chunks)


def extract_claims_from_transcript(doc: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Extract guidance, reported figures, and events using bulk task."""
    period = doc.get("period", "Unknown")
    event_date = str(doc.get("event_date") or "")
    pages = doc.get("pages") or []
    text_ok = doc.get("text_ok", True)
    template = load_claims_prompt_template()

    pdf_bytes: bytes | None = None
    if text_ok and pages:
        transcript_text = format_transcript_with_page_markers(pages)
        prompt = (
            template.replace("{period}", period)
            .replace("{event_date}", event_date)
            .replace("{transcript_text}", transcript_text)
        )
    else:
        logger.info("Transcript text_ok=False for %s; fetching raw PDF", period)
        url = doc["url"]
        resp = requests.get(url, timeout=30)
        pdf_bytes = resp.content
        prompt = (
            template.replace("{period}", period)
            .replace("{event_date}", event_date)
            .replace("{transcript_text}", "[Attached PDF Document]")
        )

    response = call_json(
        task="bulk",
        prompt=prompt,
        prompt_version="claims_v3",
        pdf_bytes=pdf_bytes,
        use_cache=True,
    )

    if not isinstance(response, dict):
        logger.warning("Unexpected non-dict response from LLM: %s", response)
        return {"guidance": [], "reported": [], "events": []}

    guidance = response.get("guidance", [])
    reported = response.get("reported", [])
    events = response.get("events", [])

    clean_reported = []
    if isinstance(reported, list):
        for r in reported:
            if isinstance(r, dict):
                r_copy = dict(r)
                if "covers" not in r_copy or not r_copy["covers"]:
                    r_copy["covers"] = r_copy.get("period", period)
                clean_reported.append(r_copy)

    clean_events = []
    if isinstance(events, list):
        for e in events:
            if isinstance(e, dict):
                clean_events.append(dict(e))

    return {
        "guidance": guidance if isinstance(guidance, list) else [],
        "reported": clean_reported,
        "events": clean_events,
    }


def verify_extracted_claims(
    doc: dict[str, Any], raw_claims: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """Step 2: Verify every quote against transcript pages in Python.
    
    Excludes non-headline business guidance like tax rate / ETR, dividend policy, accounting.
    Returns (verified_guidance, verified_reported, verified_events, total_extracted, total_verified).
    """
    pages = doc.get("pages") or []
    doc_id = doc["id"]
    period = doc.get("period", "")
    event_date = doc.get("event_date")

    raw_guidance = raw_claims.get("guidance", [])
    raw_reported = raw_claims.get("reported", [])
    raw_events = raw_claims.get("events", [])

    total_extracted = len(raw_guidance) + len(raw_reported) + len(raw_events)
    verified_guidance = []
    verified_reported = []
    verified_events = []

    for item in raw_guidance:
        statement = item.get("statement") or ""
        quote = item.get("quote", "")
        metric = normalize_metric(item.get("metric", ""), statement + " " + quote)
        segment = normalize_segment(item.get("segment"))
        statement_lower = statement.lower()

        # Hard Python exclusion for tax rates, dividend policy, accounting
        stmt_words = statement_lower.split()
        if (
            "tax rate" in statement_lower
            or "etr" in stmt_words
            or "tax %" in statement_lower
            or "effective tax" in statement_lower
            or "dividend" in statement_lower
            or "accounting" in statement_lower
        ):
            logger.info("Filtered out non-headline guidance item: %s (%s)", metric, statement[:40])
            continue

        quote = item.get("quote", "")
        page = parse_page_number(item.get("page", 1))

        if verify_quote_on_pages(quote, pages, page):
            item_copy = dict(item)
            item_copy["metric"] = metric
            item_copy["segment"] = segment
            item_copy["applies_to"] = normalize_applies_to(item.get("applies_to", ""))
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
            item_copy["metric"] = normalize_metric(item.get("metric", ""))
            item_copy["segment"] = normalize_segment(item.get("segment"))
            item_copy["document_id"] = doc_id
            item_copy["period_reported"] = period
            item_copy["event_date"] = event_date
            item_copy["page"] = page
            # If Q4 concall reports full year number, normalize covers to full FY
            if period.startswith("Q4"):
                fy_match = re.search(r"FY\s*(\d{2,4})", period)
                if fy_match:
                    fy_target = f"FY{fy_match.group(1)[-2:]}"
                    q_lower = quote.lower()
                    if (
                        f"for {fy_target.lower()}" in q_lower
                        or f"as of {fy_target.lower()}" in q_lower
                        or f"{fy_target.lower()}," in q_lower
                        or f"{fy_target.lower()} " in q_lower
                        or "full year" in q_lower
                        or "full-year" in q_lower
                        or "whole year" in q_lower
                        or f"fy'{fy_target[-2:]}" in q_lower
                        or "as of march" in q_lower
                    ):
                        item_copy["covers"] = fy_target
            verified_reported.append(item_copy)
        else:
            logger.info("Dropped unverified reported quote on %s [p.%d]: %s", period, page, quote[:60])

    for item in raw_events:
        quote = item.get("quote", "")
        page = parse_page_number(item.get("page", 1))

        if verify_quote_on_pages(quote, pages, page):
            item_copy = dict(item)
            item_copy["segment"] = normalize_segment(item.get("segment"))
            item_copy["document_id"] = doc_id
            item_copy["period_reported"] = period
            item_copy["event_date"] = event_date
            item_copy["page"] = page
            verified_events.append(item_copy)
        else:
            logger.info("Dropped unverified event quote on %s [p.%d]: %s", period, page, quote[:60])

    total_verified = len(verified_guidance) + len(verified_reported) + len(verified_events)
    return verified_guidance, verified_reported, verified_events, total_extracted, total_verified


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


def group_targets_and_build_timeline(
    guidance_items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Group guidance by (metric, segment, applies_to) across quarters.
    
    Computes midpoints and deterministically assigns revision labels.
    """
    groups: dict[tuple[str, str | None, str], list[dict[str, Any]]] = {}

    for g in guidance_items:
        metric = g.get("metric", "")
        segment = g.get("segment")
        applies_to = g.get("applies_to", "")
        if not metric or not applies_to:
            continue
        key = (metric, segment, applies_to)
        if key not in groups:
            groups[key] = []
        groups[key].append(g)

    consolidated_targets: list[dict[str, Any]] = []
    timeline_entries: list[dict[str, Any]] = []
    target_idx = 1

    sorted_group_keys = sorted(groups.keys(), key=lambda k: (k[0], k[1] or "", k[2]))

    for metric, segment, applies_to in sorted_group_keys:
        items = groups[(metric, segment, applies_to)]
        items_sorted = sorted(items, key=lambda x: str(x.get("event_date") or x.get("period_made") or ""))
        first_item = items_sorted[0]
        latest_item = items_sorted[-1]

        first_target = first_item.get("target") or {}
        latest_target = latest_item.get("target") or {}

        # Handle bps to % conversion
        for tgt in [first_target, latest_target]:
            raw_u = str(tgt.get("unit") or "").lower()
            if "bps" in raw_u or "basis" in raw_u:
                tgt["unit"] = "%"
                if tgt.get("value") is not None:
                    tgt["value"] = float(tgt["value"]) / 100.0
                if tgt.get("low") is not None:
                    tgt["low"] = float(tgt["low"]) / 100.0
                if tgt.get("high") is not None:
                    tgt["high"] = float(tgt["high"]) / 100.0

        # Determine revision label
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

        seg_prefix = f"[{segment}] " if segment else ""
        evolution_str = f"{seg_prefix}{applies_to} {metric}: " + " → ".join(steps)

        target_unit = (
            latest_target.get("unit")
            or first_target.get("unit")
            or normalize_unit(None, latest_item.get("statement", "") + " " + metric)
            or ""
        )

        t_obj = {
            "id": f"T{target_idx}",
            "metric": metric,
            "segment": segment,
            "applies_to": applies_to,
            "statement": latest_item.get("statement", first_item.get("statement", "")),
            "first_made_in": first_item.get("period_made", ""),
            "first_event_date": first_item.get("event_date", ""),
            "latest_period": latest_item.get("period_made", ""),
            "target": latest_target or first_target,
            "earliest_target": first_target,
            "revision_label": revision_label,
            "evolution": evolution_str,
            "unit": target_unit,
            "items": items_sorted,
        }
        consolidated_targets.append(t_obj)

        # Only include in timeline_entries if 2+ items AND values actually changed
        values_set = set()
        for it in items_sorted:
            td = it.get("target") or {}
            v = td.get("value") or (f"{td.get('low')}-{td.get('high')}" if td.get("low") is not None else None)
            if v is not None:
                values_set.add(str(v).strip().lower())

        has_actual_change = len(values_set) >= 2 or revision_label in ["raised", "cut", "widened", "narrowed"]

        if len(items_sorted) >= 2 and has_actual_change:
            timeline_entries.append({
                "metric": metric,
                "segment": segment,
                "applies_to": applies_to,
                "evolution": evolution_str,
                "items": items_sorted,
            })
        target_idx += 1

    return consolidated_targets, timeline_entries


def compute_financial_numbers(financials_row: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute financial numbers tagged with explicit metrics, covers periods, and units."""
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
        norm_label = label.lower()

        # Map to metric
        if "sales" in norm_label or "revenue" in norm_label:
            metric_level = "revenue"
            metric_growth = "revenue_growth"
        elif "opm" in norm_label or "operating profit margin" in norm_label or "ebitda margin" in norm_label:
            metric_level = "ebitda_margin"
            metric_growth = None
        elif "operating profit" in norm_label or "ebit" in norm_label:
            metric_level = "ebit_margin"
            metric_growth = None
        elif "net profit" in norm_label or "pat" in norm_label:
            metric_level = "pat"
            metric_growth = "pat_growth"
        else:
            continue

        is_pct = "%" in label or "margin" in norm_label
        row_unit = "%" if is_pct else "₹ cr"

        for i in range(num_cols):
            v_curr = values[i] if i < len(values) else None
            if v_curr is None:
                continue

            q_cov = q_covers_list[i]
            n_items.append({
                "id": f"N{counter}",
                "label": label,
                "metric": metric_level,
                "segment": None,
                "covers": q_cov,
                "value": v_curr,
                "unit": row_unit,
                "description": f"{label} {col_labels[i]} = {v_curr:,.1f}{row_unit}",
            })
            counter += 1

            if not is_pct:
                if i > 0:
                    v_prev = values[i - 1] if (i - 1) < len(values) else None
                    if v_prev is not None and v_prev != 0:
                        qoq = ((v_curr - v_prev) / abs(v_prev)) * 100.0
                        n_items.append({
                            "id": f"N{counter}",
                            "label": f"{label} QoQ growth",
                            "metric": metric_growth,
                            "segment": None,
                            "covers": q_cov,
                            "value": round(qoq, 1),
                            "unit": "%",
                            "description": f"{label} QoQ growth in {col_labels[i]} = {qoq:+.1f}% vs {q_covers_list[i - 1]}",
                        })
                        counter += 1

                if i >= 4:
                    v_yoy = values[i - 4] if (i - 4) < len(values) else None
                    if v_yoy is not None and v_yoy != 0:
                        yoy = ((v_curr - v_yoy) / abs(v_yoy)) * 100.0
                        n_items.append({
                            "id": f"N{counter}",
                            "label": f"{label} YoY growth",
                            "metric": metric_growth,
                            "segment": None,
                            "covers": q_cov,
                            "value": round(yoy, 1),
                            "unit": "%",
                            "description": f"{label} YoY growth in {col_labels[i]} = {yoy:+.1f}% vs {q_covers_list[i - 4]}",
                        })
                        counter += 1

        # Trailing 4 Quarters (TTM)
        if num_cols >= 8:
            last_4 = [values[j] for j in range(num_cols - 4, num_cols) if j < len(values) and values[j] is not None]
            prev_4 = [values[j] for j in range(num_cols - 8, num_cols - 4) if j < len(values) and values[j] is not None]
            if len(last_4) == 4 and len(prev_4) == 4:
                sum_last = sum(last_4)
                sum_prev = sum(prev_4)
                n_items.append({
                    "id": f"N{counter}",
                    "label": f"{label} (TTM)",
                    "metric": metric_level,
                    "segment": None,
                    "covers": "TTM",
                    "value": sum_last,
                    "unit": row_unit,
                    "description": f"{label} Trailing 4 Quarters ({q_covers_list[num_cols-4]} to {q_covers_list[num_cols-1]}) = {sum_last:,.1f}{row_unit}",
                })
                counter += 1
                if not is_pct and sum_prev != 0:
                    pct = ((sum_last - sum_prev) / abs(sum_prev)) * 100.0
                    n_items.append({
                        "id": f"N{counter}",
                        "label": f"{label} TTM YoY growth",
                        "metric": metric_growth,
                        "segment": None,
                        "covers": "TTM",
                        "value": round(pct, 1),
                        "unit": "%",
                        "description": f"{label} Trailing 4 Quarters YoY growth = {pct:+.1f}% vs prev 4Q",
                    })
                    counter += 1

    # 2. Compute H1 numbers if both Q1 and Q2 exist
    for row in rows:
        label = row.get("label", "")
        values = row.get("values", [])
        norm_label = label.lower()
        if "%" in label or "margin" in norm_label:
            continue
        metric_level = "revenue" if ("sales" in norm_label or "revenue" in norm_label) else "pat"
        metric_growth = "revenue_growth" if metric_level == "revenue" else "pat_growth"

        h1_by_fy: dict[str, float] = {}
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
                        h1_by_fy[fy_curr] = h1_val
                        n_items.append({
                            "id": f"N{counter}",
                            "label": f"{label} (H1)",
                            "metric": metric_level,
                            "segment": None,
                            "covers": h1_cov,
                            "value": h1_val,
                            "unit": "₹ cr",
                            "description": f"{label} {h1_cov} = {h1_val:,.1f} ₹ cr (sum of Q1 and Q2)",
                        })
                        counter += 1

        for fy_str, h1_val in sorted(h1_by_fy.items()):
            try:
                yr_int = int(fy_str.replace("FY", ""))
                prev_fy = f"FY{yr_int - 1:02d}"
                if prev_fy in h1_by_fy and h1_by_fy[prev_fy] != 0:
                    prev_h1 = h1_by_fy[prev_fy]
                    h1_growth = ((h1_val - prev_h1) / abs(prev_h1)) * 100.0
                    n_items.append({
                        "id": f"N{counter}",
                        "label": f"{label} H1 YoY growth",
                        "metric": metric_growth,
                        "segment": None,
                        "covers": f"H1 {fy_str}",
                        "value": round(h1_growth, 1),
                        "unit": "%",
                        "description": f"{label} H1 {fy_str} YoY growth = {h1_growth:+.1f}% vs H1 {prev_fy}",
                    })
                    counter += 1
            except Exception:
                pass

    # 3. Annual Profit & Loss
    pl_table = tables.get("profit_loss", {})
    pl_columns = pl_table.get("columns", [])
    pl_rows = pl_table.get("rows", [])
    recent_pl_indices = [idx for idx in range(max(0, len(pl_columns) - 4), len(pl_columns))]

    for row in pl_rows:
        label = row.get("label", "")
        values = row.get("values", [])
        norm_label = label.lower()
        if "sales" in norm_label or "revenue" in norm_label:
            metric_level = "revenue"
            metric_growth = "revenue_growth"
        elif "opm" in norm_label or "operating profit margin" in norm_label or "ebitda margin" in norm_label:
            metric_level = "ebitda_margin"
            metric_growth = None
        elif "net profit" in norm_label or "pat" in norm_label:
            metric_level = "pat"
            metric_growth = "pat_growth"
        else:
            continue

        is_pct = "%" in label or "margin" in norm_label
        row_unit = "%" if is_pct else "₹ cr"

        for idx in recent_pl_indices:
            if idx >= len(values) or values[idx] is None:
                continue
            val = values[idx]
            col = pl_columns[idx]
            match = re.search(r"(?:mar(?:ch)?\s*)?(\d{4})", col, re.IGNORECASE)
            if match:
                yr = match.group(1)
                fy_cov = f"FY{yr[-2:]}"
                desc = f"{label} {fy_cov} (Annual Mar {yr}) = {val:,.1f}{row_unit}"
                n_items.append({
                    "id": f"N{counter}",
                    "label": label,
                    "metric": metric_level,
                    "segment": None,
                    "covers": fy_cov,
                    "value": val,
                    "unit": row_unit,
                    "description": desc,
                })
                counter += 1

                if metric_growth and not is_pct and idx > 0 and (idx - 1) < len(values) and values[idx - 1] is not None and values[idx - 1] != 0:
                    prev_val = values[idx - 1]
                    ann_yoy = ((val - prev_val) / abs(prev_val)) * 100.0
                    n_items.append({
                        "id": f"N{counter}",
                        "label": f"{label} YoY growth",
                        "metric": metric_growth,
                        "segment": None,
                        "covers": fy_cov,
                        "value": round(ann_yoy, 1),
                        "unit": "%",
                        "description": f"{label} {fy_cov} YoY growth = {ann_yoy:+.1f}% vs prior year",
                    })
                    counter += 1

    return n_items


def is_vague_segment(seg: str | None) -> bool:
    """Return True if segment is vague or unstated (e.g. 'this vertical')."""
    if not seg:
        return False
    norm = seg.strip().lower()
    return norm in {
        "this vertical",
        "the vertical",
        "vertical",
        "this business",
        "the business",
        "this segment",
        "the segment",
        "segment",
        "business",
    }


def find_candidates_for_target(
    target: dict[str, Any],
    r_items: list[dict[str, Any]],
    n_items: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pick candidate evidence for a target: same metric and segment only.
    
    Milestones use events with same segment from later calls.
    Growth targets use computed growth % items (quarterly YoY, H1, TTM, FY).
    ebitda_margin uses screener's OPM %.
    Company-wide N items are never candidates for segment targets.
    Vague segments ('this vertical') yield no candidates -> unverifiable.
    """
    t_metric = target.get("metric", "")
    t_seg = target.get("segment")
    t_first_date = str(target.get("first_event_date") or "")
    t_first_period = target.get("first_made_in", "")

    # Vague segment with no match -> no candidates
    if is_vague_segment(t_seg):
        return []

    candidates: list[dict[str, Any]] = []

    # Case 1: Milestone target
    if t_metric == "milestone":
        t_stmt = target.get("statement", "")
        for e in events:
            e_what = e.get("what") or ""
            overlap = compute_milestone_overlap(t_stmt, e_what)
            if overlap < 0.2:
                continue

            e_seg = e.get("segment")
            seg_match = (t_seg is not None and e_seg == t_seg) or (t_seg is not None and t_seg in e_what.lower())

            if seg_match or t_seg is None:
                e_date = str(e.get("event_date") or "")
                e_period = e.get("period_reported", "")
                if (e_date and t_first_date and e_date > t_first_date) or (e_period != t_first_period):
                    candidates.append(e)
        return candidates

    # Case 2: Quantitative target
    t_applies_to = target.get("applies_to", "")

    # 2a. Match in reported items (R) with the SAME segment only and period falls inside applies_to
    for r in r_items:
        if r.get("metric") == t_metric:
            r_cov = r.get("covers") or r.get("period") or ""
            if not period_falls_inside(r_cov, t_applies_to):
                continue

            r_seg = r.get("segment")
            seg_match = False
            if t_seg is None and r_seg is None:
                seg_match = True
            elif t_seg is not None and r_seg is not None:
                t_words = set(t_seg.lower().split())
                r_words = set(r_seg.lower().split())
                if t_seg.lower() in r_seg.lower() or r_seg.lower() in t_seg.lower() or bool(t_words & r_words):
                    seg_match = True
            if seg_match:
                candidates.append(r)

    # 2b. Match in financial items (N) - whole company only. Never for segment targets!
    # Evidence covers period must fall inside target's applies_to.
    if t_seg is None:
        for n in n_items:
            if n.get("metric") == t_metric:
                n_cov = n.get("covers", "")
                if period_falls_inside(n_cov, t_applies_to):
                    candidates.append(n)

    return candidates


def evaluate_milestone(target: dict[str, Any], candidate_events: list[dict[str, Any]], latest_quarter: str) -> dict[str, Any]:
    """Judge milestone targets with events deterministically:
    - done by deadline = delivered
    - done late = partly ('late by N months')
    - delay announced = revised_down
    - deadline passed and no update = unverifiable
    - deadline in future = on_track / pending
    """
    t_id = target["id"]
    statement = target.get("statement", "")
    applies_to = target.get("applies_to", "")
    t_fy, t_q = parse_fiscal_period(applies_to)
    period_ended = has_period_ended(applies_to, latest_quarter)

    # Check for 'done' status
    done_events = [e for e in candidate_events if e.get("status") == "done"]
    if done_events:
        ev = done_events[0]
        ev_when = ev.get("when", "")
        ev_fy, ev_q = parse_fiscal_period(ev_when)

        # Check timeliness
        if (ev_fy, ev_q) <= (t_fy, t_q):
            return {
                "id": t_id,
                "promise": statement,
                "made_in": target.get("first_made_in", ""),
                "applies_to": applies_to,
                "verdict": "delivered",
                "evidence": f"Milestone delivered on time ({ev.get('what')}, {ev_when}) citing {ev['id']}",
                "evidence_ids": [ev["id"]],
                "revision_label": target.get("revision_label", "none"),
            }
        else:
            # Done late
            q_diff = (ev_fy - t_fy) * 4 + (ev_q - t_q)
            months_late = max(1, q_diff * 3)
            return {
                "id": t_id,
                "promise": statement,
                "made_in": target.get("first_made_in", ""),
                "applies_to": applies_to,
                "verdict": "partly",
                "evidence": f"Milestone completed late by {months_late} months ({ev.get('what')}, {ev_when}) citing {ev['id']}",
                "evidence_ids": [ev["id"]],
                "revision_label": target.get("revision_label", "none"),
            }

    # Check for 'delayed' status
    delayed_events = [e for e in candidate_events if e.get("status") == "delayed"]
    if delayed_events:
        ev = delayed_events[0]
        v_delayed = "missed" if period_ended else "behind"
        return {
            "id": t_id,
            "promise": statement,
            "made_in": target.get("first_made_in", ""),
            "applies_to": applies_to,
            "verdict": v_delayed,
            "evidence": f"Delay announced ({ev.get('what')}, {ev.get('when')}) citing {ev['id']}",
            "evidence_ids": [ev["id"]],
            "revision_label": "cut",
        }

    # In progress or no status change
    if period_ended:
        return {
            "id": t_id,
            "promise": statement,
            "made_in": target.get("first_made_in", ""),
            "applies_to": applies_to,
            "verdict": "unverifiable",
            "evidence": "deadline passed and no completion update in later calls",
            "evidence_ids": [e["id"] for e in candidate_events[:1]],
            "revision_label": target.get("revision_label", "none"),
        }
    else:
        ev_ids = [e["id"] for e in candidate_events[:1]]
        return {
            "id": t_id,
            "promise": statement,
            "made_in": target.get("first_made_in", ""),
            "applies_to": applies_to,
            "verdict": "on_track",
            "evidence": f"Milestone in progress towards deadline ({applies_to}) citing {ev_ids}",
            "evidence_ids": ev_ids,
            "revision_label": target.get("revision_label", "none"),
        }


def evaluate_future_multiyear_target(
    target: dict[str, Any],
    n_items: list[dict[str, Any]],
    r_items: list[dict[str, Any]],
    latest_quarter: str,
) -> dict[str, Any]:
    """Future multi-year targets (applies_to beyond current fiscal year):
    No bounds check and no LLM call. Verdict pending, plus a Python note:
    - For amounts: 'needs X% a year from ₹Y cr; growing Z% now', using TTM vs previous TTM.
    - For rates: 'now A% vs target B–C%'.
    """
    t_id = target["id"]
    statement = target.get("statement", "")
    applies_to = target.get("applies_to", "")
    t_target = target.get("target") or {}
    t_unit = target.get("unit") or t_target.get("unit") or ""
    t_metric = target.get("metric", "")
    revision_label = target.get("revision_label", "none")

    cur_fy, _ = parse_fiscal_period(latest_quarter)
    t_fy, _ = parse_fiscal_period(applies_to)
    years_ahead = max(1, t_fy - cur_fy)

    is_rate = t_unit == "%" or t_metric in ["ebitda_margin", "ebit_margin", "nim", "revenue_growth", "pat_growth", "aum_growth"]
    t_seg = target.get("segment")

    if is_rate:
        # Rate target: 'now A% vs target B–C%'
        now_rate = None
        cited_ids = []

        # 1. Look for candidate reported items matching metric, unit == "%", and segment
        for r in r_items:
            r_seg = r.get("segment")
            if r.get("metric") == t_metric and r.get("unit") == "%" and r.get("value") is not None:
                seg_ok = (t_seg is None and r_seg is None) or (t_seg is not None and r_seg is not None and (t_seg.lower() in r_seg.lower() or r_seg.lower() in t_seg.lower()))
                if seg_ok:
                    try:
                        now_rate = float(r["value"])
                        cited_ids = [r["id"]]
                        break
                    except (ValueError, TypeError):
                        pass

        # 2. Look in n_items (latest rate)
        if now_rate is None:
            matching_n = [
                n for n in n_items
                if n.get("metric") == t_metric and n.get("unit") == "%" and n.get("value") is not None and "QoQ" not in n.get("label", "")
            ]
            if matching_n:
                now_rate = float(matching_n[-1]["value"])
                cited_ids = [matching_n[-1]["id"]]

        low = t_target.get("low")
        high = t_target.get("high")
        val = t_target.get("value")
        if low is not None and high is not None:
            tgt_str = f"{float(low):g}–{float(high):g}%"
        elif val is not None:
            tgt_str = f"{float(val):g}%"
        elif low is not None:
            tgt_str = f">{float(low):g}%"
        elif high is not None:
            tgt_str = f"<{float(high):g}%"
        else:
            tgt_str = f"{target.get('statement') or 'target'}"

        if now_rate is not None:
            note = f"now {now_rate:.1f}% vs target {tgt_str}"
        else:
            note = f"target {tgt_str} (future multi-year)"

        return {
            "id": t_id,
            "promise": statement,
            "made_in": target.get("first_made_in", ""),
            "applies_to": applies_to,
            "verdict": "pending",
            "evidence": note,
            "evidence_ids": cited_ids,
            "revision_label": revision_label,
        }
    else:
        # Amount target: 'needs X% a year from ₹Y cr; growing Z% now'
        base_ttm = None
        ttm_growth = None
        cited_ids = []

        # If target has a segment, check for segment reported amount first
        if t_seg is not None:
            for r in r_items:
                r_seg = r.get("segment")
                if r_seg and (t_seg.lower() in r_seg.lower() or r_seg.lower() in t_seg.lower()):
                    if r.get("unit") != "%" and r.get("value") is not None:
                        val_f = float(r["value"])
                        cov_str = r.get("covers") or ""
                        t_len, cov_len = get_period_length_and_months_covered("FY27", cov_str)
                        multiplier = (t_len / cov_len) if cov_len > 0 else 1.0
                        base_ttm = val_f * multiplier
                        cited_ids = [r["id"]]
                        break

        # Check if USD target
        is_usd = t_unit == "$" or any(k in statement.lower() for k in ["$", "usd", "dollar"])
        if is_usd and base_ttm is None:
            usd_items = [r for r in r_items if r.get("metric") == "revenue" and ("$" in (r.get("unit") or "") or "usd" in (r.get("quote") or "").lower())]
            for r in usd_items:
                if "FY26" in (r.get("covers") or "") and r.get("value") is not None:
                    base_ttm = float(r["value"])
                    cited_ids = [r["id"]]
                    break
            if base_ttm is None and usd_items:
                val = float(usd_items[0]["value"])
                base_ttm = val * 4 if val > 100 else val
                cited_ids = [usd_items[0]["id"]]

            t_val = t_target.get("value") or t_target.get("low") or t_target.get("high")
            if base_ttm is not None and t_val is not None:
                t_val_f = float(t_val)
                if base_ttm > 100 and t_val_f < 50:
                    t_val_f = t_val_f * 1000.0
                cagr = ((t_val_f / base_ttm) ** (1.0 / years_ahead) - 1.0) * 100.0
                note = f"needs {cagr:.1f}% a year from ${base_ttm:,.0f}M; growing steadily now"
                return {
                    "id": t_id,
                    "promise": statement,
                    "made_in": target.get("first_made_in", ""),
                    "applies_to": applies_to,
                    "verdict": "pending",
                    "evidence": note,
                    "evidence_ids": cited_ids,
                    "revision_label": revision_label,
                }

        if base_ttm is None:
            for n in n_items:
                if n.get("covers") == "TTM":
                    if n.get("metric") == t_metric and n.get("unit") != "%" and base_ttm is None:
                        base_ttm = float(n["value"])
                        cited_ids.append(n["id"])
                    elif n.get("metric") in [f"{t_metric}_growth", "revenue_growth"] and n.get("unit") == "%" and ttm_growth is None:
                        ttm_growth = float(n["value"])
                        cited_ids.append(n["id"])

        if base_ttm is None:
            for n in n_items:
                if n.get("covers") == "TTM" and n.get("unit") == "₹ cr" and base_ttm is None:
                    base_ttm = float(n["value"])
                    cited_ids.append(n["id"])

        t_val = t_target.get("value") or t_target.get("low") or t_target.get("high")
        if t_val is None or (isinstance(t_val, (int, float)) and t_val < 1000 and "lakh crore" in statement.lower()):
            t_val = 100000.0

        if base_ttm is not None and t_val is not None:
            try:
                t_val_f = float(t_val)
                if t_val_f < 1000 and "lakh crore" in statement.lower():
                    t_val_f = 100000.0

                cagr = ((t_val_f / base_ttm) ** (1.0 / years_ahead) - 1.0) * 100.0
                z_str = f"{ttm_growth:+.1f}%" if ttm_growth is not None else "0.0%"
                note = f"needs {cagr:.1f}% a year from ₹{base_ttm:,.0f} cr; growing {z_str} now"
            except Exception:
                note = f"future multi-year target ({applies_to})"
        elif ttm_growth is not None:
            note = f"growing {ttm_growth:+.1f}% now (TTM)"
        else:
            note = f"future multi-year target ({applies_to})"

        return {
            "id": t_id,
            "promise": statement,
            "made_in": target.get("first_made_in", ""),
            "applies_to": applies_to,
            "verdict": "pending",
            "evidence": note,
            "evidence_ids": cited_ids,
            "revision_label": revision_label,
        }


def format_override_evidence_sentence(
    target: dict[str, Any],
    evidence_item: dict[str, Any],
    effective_val: float,
    multiplier: float,
    low_f: float,
    high_f: float,
    ev_ids: list[str],
    t_unit_norm: str | None,
) -> str:
    """Format deterministic evidence sentence when Python rule overrides a verdict.
    
    Example: 'FY26 revenue growth 25.8% (N173) vs 50% guided'
    """
    metric = target.get("metric", "")
    metric_names = {
        "revenue_growth": "revenue growth",
        "pat_growth": "PAT growth",
        "aum_growth": "AUM growth",
        "credit_cost": "credit cost",
        "ebitda_margin": "EBITDA margin",
        "ebit_margin": "EBIT margin",
        "revenue": "revenue",
        "pat": "PAT",
        "order_book": "order book",
        "store_count": "store count",
        "volume": "volume",
        "capacity": "capacity",
        "capex": "capex",
        "nim": "NIM",
    }
    metric_name = metric_names.get(metric, metric.replace("_", " "))
    applies_to = target.get("applies_to", "")
    covers = evidence_item.get("covers") or applies_to
    
    eid_str = ", ".join(ev_ids) if ev_ids else evidence_item.get("id", "")
    is_pct = t_unit_norm == "%"
    
    # Format guided target
    t_target = target.get("target") or {}
    is_currency = t_unit_norm in ["₹ cr", "cr", "inr cr"]

    if is_currency:
        if t_target.get("value") is not None:
            guided_str = format_money(t_target["value"], "cr")
        elif t_target.get("low") is not None and t_target.get("high") is not None:
            guided_str = format_money_range(t_target["low"], t_target["high"], "cr")
        else:
            guided_str = format_money_range(low_f, high_f, "cr")

        effective_str = format_money(effective_val, "cr")
        if multiplier > 1.0:
            return f"{covers} {metric_name} at current run-rate: {effective_str} ({eid_str}) vs {guided_str} guided"
        else:
            return f"{covers} {metric_name}: {effective_str} ({eid_str}) vs {guided_str} guided"

    elif is_pct:
        if t_target.get("value") is not None:
            try:
                guided_str = f"{float(t_target['value']):.1f}%"
            except (ValueError, TypeError):
                guided_str = f"{t_target['value']}%"
        elif t_target.get("low") is not None and t_target.get("high") is not None:
            guided_str = f"{float(t_target['low']):.1f}–{float(t_target['high']):.1f}%"
        else:
            guided_str = f"{low_f:.1f}–{high_f:.1f}%"

        val_str = f"{effective_val:.1f}%"
        return f"{covers} {metric_name} {val_str} ({eid_str}) vs {guided_str} guided"

    else:
        u_suffix = f" {t_unit_norm}" if t_unit_norm else ""
        if t_target.get("value") is not None:
            guided_str = f"{format_indian_number(t_target['value'])}{u_suffix}"
        elif t_target.get("low") is not None and t_target.get("high") is not None:
            guided_str = f"{format_indian_number(t_target['low'])}–{format_indian_number(t_target['high'])}{u_suffix}"
        else:
            guided_str = f"{format_indian_number(low_f)}–{format_indian_number(high_f)}{u_suffix}"

        val_str = f"{format_indian_number(effective_val)}{u_suffix}"
        if multiplier > 1.0:
            return f"{covers} {metric_name} at current run-rate: {val_str} ({eid_str}) vs {guided_str} guided"
        else:
            return f"{covers} {metric_name} {val_str} ({eid_str}) vs {guided_str} guided"


def apply_python_overrides_and_runrates(
    raw_verdicts: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    candidates_by_tid: dict[str, list[dict[str, Any]]],
    latest_quarter: str,
) -> tuple[list[dict[str, Any]], int]:
    """Execute deterministic post-checks that override the model:
    
    1. For amounts (₹ cr, units, stores), computes run-rate = sum so far * (period len / months covered)
       and bounds check uses run-rate, labelled 'at current run-rate'.
    2. Rates (%) compare directly.
    3. If period has ended with partial evidence only: verdict is likely_delivered or likely_missed,
       with note '(based on {covers}: run-rate ₹X cr)'.
    4. Numeric range sanity check:
       - If value/run-rate > high: ahead (running period) or delivered with '(beat)' (ended period).
       - If within range: on_track (running period) or delivered (ended period).
       - If < low: behind (running period) or missed (ended period).
    """
    overrides_count = 0
    final_verdicts: list[dict[str, Any]] = []

    model_v_by_id = {v["id"]: v for v in raw_verdicts if isinstance(v, dict) and "id" in v}

    for t in targets:
        t_id = t["id"]
        statement = t.get("statement", "")
        applies_to = t.get("applies_to", "")
        applies_to_norm = normalize_period(applies_to)
        revision_label = t.get("revision_label", "none")
        candidates = candidates_by_tid.get(t_id, [])
        cand_by_id = {c["id"]: c for c in candidates}
        period_ended = has_period_ended(applies_to, latest_quarter)

        if t_id not in model_v_by_id:
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
        if verdict in ["revised_up", "revised_down"]:
            verdict = "on_track" if verdict == "revised_up" else ("missed" if period_ended else "behind")
            overrides_count += 1

        evidence_text = (raw_v.get("evidence") or "").strip()
        ev_ids = raw_v.get("evidence_ids") or []
        if isinstance(ev_ids, str):
            ev_ids = [ev_ids]

        # 1. Validate Evidence IDs
        valid_cites = [eid for eid in ev_ids if eid in cand_by_id]
        if not valid_cites and verdict not in ["unverifiable", "pending"]:
            logger.warning("Override [%s]: %s -> unverifiable (no valid candidate evidence IDs)", t_id, verdict)
            verdict = "unverifiable"
            evidence_text = "unreferenced candidate evidence ID"
            overrides_count += 1
            ev_ids = []
        else:
            ev_ids = valid_cites

        cited_items = [cand_by_id[eid] for eid in ev_ids]

        # 2. Unit Matching Check
        target_unit = t.get("unit") or (t.get("target") or {}).get("unit")
        t_unit_norm = normalize_unit(target_unit, statement + " " + t.get("metric", ""))

        if t_unit_norm is not None and cited_items:
            has_matching_unit = any(
                normalize_unit(e.get("unit"), e.get("description", "") or e.get("quote", "")) == t_unit_norm
                for e in cited_items
            )
            if not has_matching_unit and verdict not in ["unverifiable", "pending"]:
                orig_v = verdict
                verdict = "unverifiable"
                evidence_text = f"evidence unit mismatch vs guided {t_unit_norm}"
                overrides_count += 1
                logger.warning("Override [%s]: %s -> unverifiable (unit mismatch: guided %s)", t_id, orig_v, t_unit_norm)

        # 3. Period Completeness Check
        has_matching_covers = False
        for e in cited_items:
            c_norm = normalize_period(e.get("covers"))
            if c_norm and c_norm == applies_to_norm:
                has_matching_covers = True
                break

        is_partial = not has_matching_covers

        # 4. Numeric Bounds Check (Run-Rate for amounts, Direct for rates)
        t_target = t.get("target") or {}
        low = t_target.get("low")
        high = t_target.get("high")
        if low is None and high is None and t_target.get("value") is not None:
            try:
                v_num = float(t_target["value"])
                low = v_num * 0.95
                high = v_num * 1.05
            except (ValueError, TypeError):
                pass

        # Exclude delta targets (e.g. 100 basis points improvement) from comparing absolute margin against delta number
        if "basis point" in statement.lower() or "bps" in statement.lower():
            low = None
            high = None

        if low is not None and high is not None and cited_items:
            try:
                low_f = float(low)
                high_f = float(high)

                is_amount = t_unit_norm != "%"
                matching_evs = [
                    e for e in cited_items
                    if normalize_unit(e.get("unit"), e.get("description", "") or e.get("quote", "")) == t_unit_norm
                    and e.get("value") is not None
                ]

                if matching_evs:
                    e = matching_evs[0]
                    val_f = float(e["value"])
                    covers_str = e.get("covers", "")

                    if t_unit_norm == "$":
                        if val_f > 100 and high_f < 50:
                            high_f = high_f * 1000.0
                            low_f = low_f * 1000.0
                        elif val_f < 50 and high_f > 100:
                            val_f = val_f * 1000.0

                    # Period check: evidence covers period must fall inside target applies_to
                    if not period_falls_inside(covers_str, applies_to):
                        logger.warning(
                            "Evidence covers %s outside target applies_to %s for target %s",
                            covers_str, applies_to, t_id
                        )
                        continue

                    if is_amount:
                        t_len, cov_len = get_period_length_and_months_covered(applies_to, covers_str)
                        multiplier = (t_len / cov_len) if cov_len > 0 else 1.0
                        effective_val = val_f * multiplier
                        u_str = f" {t_unit_norm}" if t_unit_norm else " cr"
                        run_rate_label = f" (run-rate: {effective_val:,.1f}{u_str})" if multiplier > 1.0 else ""
                    else:
                        multiplier = 1.0
                        effective_val = val_f
                        run_rate_label = ""

                    # Direction by metric:
                    # - Capex is neutral: above_plan / within_plan / below_plan
                    # - Credit cost: lower is better (below range is good)
                    # - Revenue, margins, growth, volume: higher is better
                    metric = t.get("metric", "")
                    if metric == "capex":
                        if effective_val > high_f:
                            new_v = "above_plan"
                        elif effective_val < low_f:
                            new_v = "below_plan"
                        else:
                            new_v = "within_plan"
                    elif metric == "credit_cost":
                        if effective_val < low_f:
                            new_v = ("likely_delivered" if is_partial else "delivered") if period_ended else "ahead"
                        elif effective_val > high_f:
                            new_v = ("likely_missed" if is_partial else "missed") if period_ended else "behind"
                        else:
                            new_v = ("likely_delivered" if is_partial else "delivered") if period_ended else "on_track"
                    else:
                        if effective_val > high_f:
                            new_v = ("likely_delivered" if is_partial else "delivered") if period_ended else "ahead"
                        elif effective_val < low_f:
                            new_v = ("likely_missed" if is_partial else "missed") if period_ended else "behind"
                        else:
                            new_v = ("likely_delivered" if is_partial else "delivered") if period_ended else "on_track"

                    if verdict != new_v:
                        orig_v = verdict
                        verdict = new_v
                        overrides_count += 1
                        evidence_text = format_override_evidence_sentence(
                            target=t,
                            evidence_item=e,
                            effective_val=effective_val,
                            multiplier=multiplier,
                            low_f=low_f,
                            high_f=high_f,
                            ev_ids=ev_ids,
                            t_unit_norm=t_unit_norm,
                        )
                        logger.warning("Override [%s]: %s -> %s (effective %s vs [%s, %s])", t_id, orig_v, verdict, effective_val, low_f, high_f)

            except (ValueError, TypeError):
                pass
        else:
            # Non-numeric or range unavailable
            if is_partial and verdict in ["delivered", "missed", "partly"]:
                orig_v = verdict
                if period_ended:
                    verdict = "likely_delivered" if orig_v == "delivered" else "likely_missed"
                    evidence_text = f"partial period ({covers_str})"
                else:
                    verdict = "on_track" if orig_v == "delivered" else "behind"
                    evidence_text = f"partial period ({covers_str})"
                overrides_count += 1
                logger.warning("Override [%s]: %s -> %s (partial period: guided %s)", t_id, orig_v, verdict)

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
    events_items: list[dict[str, Any]],
    latest_quarter: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Step 3: Judge delivery with candidate pre-filtering, milestone evaluation, and LLM."""
    # Index reported items R1...
    indexed_r = []
    for idx, r in enumerate(reported_items, start=1):
        r_copy = dict(r)
        r_copy["id"] = f"R{idx}"
        indexed_r.append(r_copy)

    # Index event items E1...
    indexed_e = []
    for idx, e in enumerate(events_items, start=1):
        e_copy = dict(e)
        e_copy["id"] = f"E{idx}"
        indexed_e.append(e_copy)

    # Pre-filter candidate evidence per target in Python
    candidates_by_tid: dict[str, list[dict[str, Any]]] = {}
    targets_needing_llm: list[dict[str, Any]] = []
    auto_resolved_verdicts: list[dict[str, Any]] = []

    cur_fy, _ = parse_fiscal_period(latest_quarter)

    for t in targets:
        t_id = t["id"]
        cands = find_candidates_for_target(t, indexed_r, n_items, indexed_e)
        candidates_by_tid[t_id] = cands

        t_fy, _ = parse_fiscal_period(t.get("applies_to", ""))

        if t_fy > cur_fy:
            # Future multi-year target (applies_to beyond current fiscal year)
            # No bounds check and no LLM call. Verdict pending + Python note.
            mv = evaluate_future_multiyear_target(t, n_items, indexed_r, latest_quarter)
            auto_resolved_verdicts.append(mv)
        elif not cands:
            # Zero candidates -> Python sets verdict with NO LLM call
            period_ended = has_period_ended(t.get("applies_to", ""), latest_quarter)
            t_seg = t.get("segment")
            if is_vague_segment(t_seg):
                v_status = "unverifiable"
                ev_str = f"vague segment ('{t_seg}') with no matching reported data"
            elif t_seg is not None:
                if not period_ended:
                    v_status = "pending"
                    ev_str = f"no reported data for segment '{t_seg}' in subsequent calls yet"
                else:
                    v_status = "unverifiable"
                    ev_str = f"no reported data for segment '{t_seg}' in subsequent calls"
            elif not period_ended:
                v_status = "pending"
                ev_str = "period running; no candidate figure or update in later calls yet"
            else:
                v_status = "unverifiable"
                ev_str = "no figure or update in later calls"

            auto_resolved_verdicts.append({
                "id": t_id,
                "promise": t.get("statement", ""),
                "made_in": t.get("first_made_in", ""),
                "applies_to": t.get("applies_to", ""),
                "verdict": v_status,
                "evidence": ev_str,
                "evidence_ids": [],
                "revision_label": t.get("revision_label", "none"),
            })
        elif t.get("metric") == "milestone":
            # Milestone targets with candidate events evaluated deterministically
            mv = evaluate_milestone(t, cands, latest_quarter)
            auto_resolved_verdicts.append(mv)
        else:
            targets_needing_llm.append(t)

    # Run reasoning model ONLY for targets needing LLM evaluation
    raw_model_verdicts = []

    if targets_needing_llm:
        t_with_cands_list = []
        for t in targets_needing_llm:
            t_id = t["id"]
            cands = candidates_by_tid[t_id]
            t_unit = t.get("unit") or ""
            is_amount = t_unit != "%"

            cand_descs = []
            for c in cands:
                c_id = c["id"]
                c_val = c.get("value")
                c_cov = c.get("covers") or c.get("period_reported") or ""
                if is_amount and c_val is not None:
                    t_len, cov_len = get_period_length_and_months_covered(t.get("applies_to", ""), c_cov)
                    multiplier = (t_len / cov_len) if cov_len > 0 else 1.0
                    run_rate = float(c_val) * multiplier
                    rr_note = f" (run-rate: {run_rate:,.1f}{t_unit} at current run-rate)" if multiplier > 1.0 else ""
                else:
                    rr_note = ""

                desc = c.get("description") or c.get("quote") or c.get("what") or ""
                cand_descs.append(f"    - [{c_id}] ({c_cov}): {desc} {rr_note}")

            t_desc = (
                f"[{t_id}] Metric: {t.get('metric')}; Segment: {t.get('segment')}; Applies to: {t.get('applies_to')}; "
                f"Statement: \"{t.get('statement')}\"; Target: {t.get('target')}; Unit: {t_unit}\n"
                f"  Candidate Evidence:\n" + "\n".join(cand_descs)
            )
            t_with_cands_list.append(t_desc)

        prompt_targets = "\n\n".join(t_with_cands_list)
        template = load_verdicts_prompt_template()
        prompt = template.replace("{ticker}", ticker).replace("{targets_with_candidates}", prompt_targets)

        response = call_json(
            task="reasoning",
            prompt=prompt,
            prompt_version="verdicts_v3",
            use_cache=True,
        )

        if isinstance(response, dict):
            raw_model_verdicts = response.get("verdicts", [])

    # Apply overrides and bounds checks
    validated_model_verdicts, overrides_count = apply_python_overrides_and_runrates(
        raw_verdicts=raw_model_verdicts,
        targets=targets_needing_llm,
        candidates_by_tid=candidates_by_tid,
        latest_quarter=latest_quarter,
    )

    all_verdicts = auto_resolved_verdicts + validated_model_verdicts
    all_verdicts.sort(key=lambda v: int("".join(c for c in v["id"] if c.isdigit()) or 999))

    # Executive read generated after overrides via small bulk call
    verdict_lines = [
        f"- {v['promise']} ({v['applies_to']}): {v['verdict']} [Rev: {v.get('revision_label', 'none')}] — {v.get('evidence', '')}"
        for v in all_verdicts
    ]
    verdicts_summary = "\n".join(verdict_lines)
    read_template_path = Path(__file__).resolve().parent / "prompts" / "read_v4.txt"
    if read_template_path.exists():
        read_template = read_template_path.read_text(encoding="utf-8")
    else:
        read_template = (
            "You are an equity research analyst summarizing management credibility for {ticker}.\n"
            "{verdicts_summary}\n"
            "Return JSON: {\"read\": \"...\"}"
        )
    read_prompt = read_template.replace("{ticker}", ticker).replace("{verdicts_summary}", verdicts_summary)
    read_resp = call_json(
        task="bulk",
        prompt=read_prompt,
        prompt_version="read_v4",
        use_cache=True,
    )
    read_text = read_resp.get("read", "") if isinstance(read_resp, dict) else ""

    # Clean any subjective praise/judgment words if present
    bad_words = ["solid", "strong", "robust", "well-managed", "impressive", "healthy", "commendable", "prudent"]
    for bw in bad_words:
        read_text = re.sub(rf"\b(?:a\s+)?{bw}\b", "", read_text, flags=re.IGNORECASE)
    read_text = re.sub(r"\s+", " ", read_text).strip()

    # Tally counts
    counts_dict: dict[str, int] = {
        "delivered": 0,
        "likely_delivered": 0,
        "ahead": 0,
        "on_track": 0,
        "behind": 0,
        "likely_missed": 0,
        "missed": 0,
        "partly": 0,
        "above_plan": 0,
        "within_plan": 0,
        "below_plan": 0,
        "pending": 0,
        "unverifiable": 0,
        "not_judged": 0,
    }
    for v in all_verdicts:
        v_name = v.get("verdict", "unverifiable")
        if v_name in counts_dict:
            counts_dict[v_name] += 1
        else:
            counts_dict["unverifiable"] += 1

    total_promises = len(all_verdicts)
    counts_parts = [f"{total_promises} promises"]
    if counts_dict["delivered"]:
        counts_parts.append(f"{counts_dict['delivered']} delivered")
    if counts_dict["likely_delivered"]:
        counts_parts.append(f"{counts_dict['likely_delivered']} likely delivered")
    if counts_dict["ahead"]:
        counts_parts.append(f"{counts_dict['ahead']} ahead")
    if counts_dict["on_track"]:
        counts_parts.append(f"{counts_dict['on_track']} on track")
    if counts_dict["within_plan"]:
        counts_parts.append(f"{counts_dict['within_plan']} within plan")
    if counts_dict["above_plan"]:
        counts_parts.append(f"{counts_dict['above_plan']} above plan")
    if counts_dict["below_plan"]:
        counts_parts.append(f"{counts_dict['below_plan']} below plan")
    if counts_dict["behind"]:
        counts_parts.append(f"{counts_dict['behind']} behind")
    if counts_dict["likely_missed"]:
        counts_parts.append(f"{counts_dict['likely_missed']} likely missed")
    if counts_dict["missed"]:
        counts_parts.append(f"{counts_dict['missed']} missed")
    if counts_dict["partly"]:
        counts_parts.append(f"{counts_dict['partly']} partly")
    if counts_dict["pending"]:
        counts_parts.append(f"{counts_dict['pending']} pending")
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

    # Gather sources for UI
    t_by_id = {t["id"]: t for t in targets}
    r_by_id = {r["id"]: r for r in indexed_r}
    e_by_id = {e["id"]: e for e in indexed_e}
    cited_sources = []

    for v in all_verdicts:
        t_id = v.get("id")
        if t_id in t_by_id:
            for it in t_by_id[t_id].get("items", []):
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
            elif eid in e_by_id:
                e_src = e_by_id[eid]
                cited_sources.append({
                    "id": eid,
                    "kind": "event",
                    "document_id": e_src.get("document_id"),
                    "period": e_src.get("period_reported"),
                    "quote": e_src.get("quote"),
                    "page": e_src.get("page"),
                })

    result_payload = {
        "verdicts": all_verdicts,
        "read": read_text or "Evaluation of management commitments across financial results and operational disclosures.",
        "counts": counts_line,
        "counts_breakdown": counts_dict,
        "revision_breakdown": rev_dict,
        "overrides_count": overrides_count,
        "total_promises": total_promises,
        "targets": [
            {
                "id": t["id"],
                "metric": t["metric"],
                "segment": t.get("segment"),
                "applies_to": t["applies_to"],
                "statement": t["statement"],
                "revision_label": t["revision_label"],
                "evolution": t["evolution"],
            }
            for t in targets
        ],
    }
    return result_payload, cited_sources


def run_promises_for_ticker(ticker: str, on_step: Any = None) -> dict[str, Any]:
    """Execute full promises pipeline (v3) for a ticker."""
    ticker = ticker.strip().upper()
    logger.info("Running promises evaluation (v3) for %s", ticker)

    if on_step:
        try:
            on_step("Reading earnings calls")
        except Exception:
            pass

    # 1. Fetch transcripts
    client = get_client()
    res = client.table("documents").select("*").eq("ticker", ticker).eq("kind", "transcript").order("event_date", desc=True).execute()
    transcripts = res.data or []
    if not transcripts:
        raise ValueError(f"No transcripts found for ticker {ticker}. Run research/build_corpus.py first.")

    latest_quarter = transcripts[0].get("period", "Q2 FY27")

    # 2. Fetch financials table
    f_res = client.table("financials").select("*").eq("ticker", ticker).execute()
    financials_row = f_res.data[0] if f_res.data else {}

    # Step 1 & 2: Extract & Verify per transcript
    all_verified_guidance = []
    all_verified_reported = []
    all_verified_events = []
    total_quotes_extracted = 0
    total_quotes_verified = 0

    for doc in transcripts:
        period = doc.get("period", "")
        raw_claims = extract_claims_from_transcript(doc)
        v_guidance, v_reported, v_events, extracted_cnt, verified_cnt = verify_extracted_claims(doc, raw_claims)
        total_quotes_extracted += extracted_cnt
        total_quotes_verified += verified_cnt
        all_verified_guidance.extend(v_guidance)
        all_verified_reported.extend(v_reported)
        all_verified_events.extend(v_events)
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

    # Step 3: Judge with pre-filtered candidates, run-rates, milestone evaluation
    if on_step:
        try:
            on_step("Checking promises against results")
        except Exception:
            pass
    judgement, cited_sources = judge_promises_for_company(
        ticker=ticker,
        targets=targets,
        timeline_entries=timeline_entries,
        reported_items=all_verified_reported,
        n_items=n_items,
        events_items=all_verified_events,
        latest_quarter=latest_quarter,
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
            "segment": t.get("segment"),
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
    print(f"PROMISES EVALUATION (v3): {res['ticker']}")
    print("=" * 70)
    print(f"Quotes: {res['quotes_extracted']} extracted, {res['quotes_verified']} verified")
    print(f"Targets: {res['unique_targets']} unique targets")
    print(f"Overrides: {res['overrides_count']}")
    print(f"Counts: {res['counts']}")
    print(f"Read: {res['read']}")
    print("\nVerdicts:")
    for v in res["verdicts"]:
        print(f"  [{v.get('id')}] {v.get('promise')} ({v.get('applies_to')}): {v.get('verdict')} [Rev: {v.get('revision_label')}]")
        print(f"       Evidence: {v.get('evidence')} (IDs: {v.get('evidence_ids')})")
    print("=" * 70 + "\n")
