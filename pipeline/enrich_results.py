"""Financial results enrichment pipeline for FINN.

Design rule: The LLM only copies numbers from the PDF; Python does all the maths.

Workflow:
1. Identify results events from the last 45 days without enrichment.results.
2. Group filings into 3-hour events, prioritize PDF candidates (e.g. Outcome of Board Meeting).
3. Download (cached locally), trim to first 15 pages with pypdf, and extract numbers via Gemini reasoning model.
4. Python converts numbers to ₹ crore, computes EBITDA, growth rates (QoQ, YoY), margins, sanity check,
   and generates the Python-derived headline.
5. Persists enrichment.results and updated summary to Supabase.
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
import requests
import pypdf

# Ensure Windows terminal supports UTF-8 (₹, ▲, ▼, −)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.db import get_client, select, upsert
from pipeline.llm import call_json

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_results")

# Suppress verbose httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

CACHE_PDF_DIR = PROJECT_ROOT / "pipeline" / "cache" / "pdfs"
CACHE_PDF_DIR.mkdir(parents=True, exist_ok=True)

PROMPT_FILE = PROJECT_ROOT / "pipeline" / "prompts" / "results_v2.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def load_prompt_template() -> str:
    """Load results extraction prompt template from pipeline/prompts/results_v1.txt."""
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found at {PROMPT_FILE}")
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def download_pdf(url: str) -> bytes:
    """Download PDF with browser User-Agent, exponential backoff, and local disk cache."""
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


def trim_pdf_pages(pdf_bytes: bytes, max_pages: int = 15) -> bytes:
    """Trim PDF to at most max_pages using pypdf."""
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


def parse_unit_factor(unit_str: str) -> float:
    """Parse printed statement unit into multiplier to convert numbers into ₹ crore."""
    if not unit_str:
        raise ValueError("Empty or missing unit in extracted results")

    u = unit_str.lower().strip()
    if "crore" in u or "cr" in u:
        return 1.0
    elif "lakh" in u or "lac" in u:
        return 0.01
    elif "million" in u or "mn" in u:
        return 0.1
    elif "thousand" in u:
        return 0.0001
    elif "rupee" in u or "inr" in u or "rs" in u:
        return 0.0000001
    else:
        raise ValueError(f"Unrecognized financial statement unit: '{unit_str}'")


def clean_num(val: Any, factor: float) -> float | None:
    """Convert raw extracted number string or float into ₹ crore."""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return round(float(val) * factor, 2)
        if isinstance(val, str):
            cleaned = val.replace(",", "").strip()
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = f"-{cleaned[1:-1]}"
            if cleaned.lower() in ("-", "nil", "null", "na", "n.a.", ""):
                return None
            return round(float(cleaned) * factor, 2)
    except Exception:
        return None
    return None


def compute_growth(curr: float | None, past: float | None) -> tuple[float | None, str | None]:
    """Calculate QoQ or YoY growth %, handling sign flips and zero baselines."""
    if curr is None or past is None:
        return None, None
    if past <= 0:
        if past < 0 and curr > 0:
            return None, "turned profitable"
        elif past <= 0 and curr <= 0:
            return None, "n.m."
        elif past == 0:
            return None, "n.m."
    if past > 0:
        if curr < 0:
            return None, "turned to loss"
        growth = ((curr - past) / past) * 100.0
        return round(growth, 1), None
    return None, None


def compute_ebitda(
    period: str, lines: dict[str, Any], factor: float, is_lender: bool
) -> float | None:
    """Compute EBITDA in ₹ crore according to FINN design rules."""
    if is_lender:
        return None

    def val(name: str) -> float | None:
        return clean_num((lines.get(name) or {}).get(period), factor)

    pbet = val("profit_before_exceptional_items_and_tax")
    pbt = val("profit_before_tax")
    exc = val("exceptional_items") or 0.0
    fin = val("finance_costs") or 0.0
    dep = val("depreciation") or 0.0
    oth = val("other_income") or 0.0

    if pbet is not None:
        return round(pbet + fin + dep - oth, 2)
    elif pbt is not None:
        # Report exceptional_items as effect on profit: a loss is negative, a gain is positive
        # Operating profit before exceptional items = pbt - exc
        return round((pbt - exc) + fin + dep - oth, 2)
    return None


def build_headline(rev_yoy: tuple[float | None, str | None], pat_yoy: tuple[float | None, str | None]) -> str:
    """Generate human-readable headline in Python from computed YoY metrics."""
    rev_pct, rev_lbl = rev_yoy
    pat_pct, pat_lbl = pat_yoy

    if rev_lbl:
        rev_part = f"Revenue {rev_lbl}"
    elif rev_pct is not None:
        sign = "+" if rev_pct >= 0 else "−"
        rev_part = f"Revenue {sign}{abs(rev_pct):.0f}% YoY"
    else:
        rev_part = "Revenue steady YoY"

    if pat_lbl:
        pat_part = f"PAT {pat_lbl}"
    elif pat_pct is not None:
        sign = "+" if pat_pct >= 0 else "−"
        pat_part = f"PAT {sign}{abs(pat_pct):.0f}% YoY"
    else:
        pat_part = "PAT steady YoY"

    return f"{rev_part}, {pat_part}"


def process_results_data(raw_data: dict[str, Any], source_pdf_url: str) -> dict[str, Any]:
    """Calculate all financial metrics, margins, sanity check, and headline."""
    unit = raw_data.get("unit") or ""
    factor = parse_unit_factor(unit)
    is_lender = bool(raw_data.get("is_lender", False))
    lines = raw_data.get("lines") or {}
    periods = raw_data.get("periods") or {}

    def get_line(name: str) -> dict[str, float | None]:
        return {
            "current": clean_num((lines.get(name) or {}).get("current"), factor),
            "previous_quarter": clean_num((lines.get(name) or {}).get("previous_quarter"), factor),
            "year_ago": clean_num((lines.get(name) or {}).get("year_ago"), factor),
        }

    rev = get_line("revenue_from_operations")
    pbt = get_line("profit_before_tax")
    tax = get_line("tax_expense")
    pat_total = get_line("profit_after_tax")
    pat_owners = get_line("pat_attributable_to_owners")
    share_associates = get_line("share_of_associates_jv")
    associates_after_tax = bool(raw_data.get("associates_after_tax", False))

    # Displayed PAT: show pat_attributable_to_owners when printed, else pat_total
    pat_display: dict[str, float | None] = {}
    for p in ("current", "previous_quarter", "year_ago"):
        if pat_owners[p] is not None:
            pat_display[p] = pat_owners[p]
        else:
            pat_display[p] = pat_total[p]

    # EBITDA
    ebitda = {
        p: compute_ebitda(p, lines, factor, is_lender)
        for p in ("current", "previous_quarter", "year_ago")
    }

    # Growth rates
    rev_qoq = compute_growth(rev["current"], rev["previous_quarter"])
    rev_yoy = compute_growth(rev["current"], rev["year_ago"])

    ebitda_qoq = compute_growth(ebitda["current"], ebitda["previous_quarter"])
    ebitda_yoy = compute_growth(ebitda["current"], ebitda["year_ago"])

    pbt_qoq = compute_growth(pbt["current"], pbt["previous_quarter"])
    pbt_yoy = compute_growth(pbt["current"], pbt["year_ago"])

    pat_qoq = compute_growth(pat_display["current"], pat_display["previous_quarter"])
    pat_yoy = compute_growth(pat_display["current"], pat_display["year_ago"])

    # EBITDA margin
    margin_curr = (
        round((ebitda["current"] / rev["current"]) * 100.0, 1)
        if ebitda["current"] is not None and rev["current"] and rev["current"] > 0
        else None
    )
    margin_year_ago = (
        round((ebitda["year_ago"] / rev["year_ago"]) * 100.0, 1)
        if ebitda["year_ago"] is not None and rev["year_ago"] and rev["year_ago"] > 0
        else None
    )
    margin_change_pp = (
        round(margin_curr - margin_year_ago, 1)
        if margin_curr is not None and margin_year_ago is not None
        else None
    )

    # Sanity check: PBT − total tax (+ associates if printed after tax) ≈ total PAT within 2%
    pbt_curr = pbt["current"]
    tax_curr = tax["current"]
    total_pat_curr = pat_total["current"]
    assoc_curr = share_associates["current"] or 0.0

    check = True
    check_diff = 0.0
    if pbt_curr is not None and total_pat_curr is not None:
        assoc_adj = assoc_curr if associates_after_tax else 0.0
        if tax_curr is not None:
            # In Indian financial statements, tax is often printed in parentheses (e.g. (1,018)),
            # which clean_num converts to negative. As an expense, it is subtracted: PBT - |tax|.
            # In case of a genuine net tax credit (e.g. Nazara), it adds to profit: PBT - tax.
            diff_expense = abs((pbt_curr - abs(tax_curr) + assoc_adj) - total_pat_curr)
            diff_credit = abs((pbt_curr - tax_curr + assoc_adj) - total_pat_curr)
            check_diff = min(diff_expense, diff_credit)
        else:
            check_diff = abs((pbt_curr + assoc_adj) - total_pat_curr)
        tolerance = 0.02 * max(abs(total_pat_curr), 1.0)
        check = check_diff <= tolerance

    headline = build_headline(rev_yoy, pat_yoy)

    return {
        "headline": headline,
        "results": {
            "basis": raw_data.get("basis", "consolidated"),
            "unit": "₹ cr",
            "periods": periods,
            "metrics": {
                "revenue": {
                    "current": rev["current"],
                    "previous_quarter": rev["previous_quarter"],
                    "year_ago": rev["year_ago"],
                    "qoq_pct": rev_qoq[0],
                    "qoq_label": rev_qoq[1],
                    "yoy_pct": rev_yoy[0],
                    "yoy_label": rev_yoy[1],
                },
                "ebitda": {
                    "current": ebitda["current"],
                    "previous_quarter": ebitda["previous_quarter"],
                    "year_ago": ebitda["year_ago"],
                    "qoq_pct": ebitda_qoq[0],
                    "qoq_label": ebitda_qoq[1],
                    "yoy_pct": ebitda_yoy[0],
                    "yoy_label": ebitda_yoy[1],
                    "margin_pct": margin_curr,
                    "margin_change_pp": margin_change_pp,
                },
                "pbt": {
                    "current": pbt["current"],
                    "previous_quarter": pbt["previous_quarter"],
                    "year_ago": pbt["year_ago"],
                    "qoq_pct": pbt_qoq[0],
                    "qoq_label": pbt_qoq[1],
                    "yoy_pct": pbt_yoy[0],
                    "yoy_label": pbt_yoy[1],
                },
                "pat": {
                    "current": pat_display["current"],
                    "previous_quarter": pat_display["previous_quarter"],
                    "year_ago": pat_display["year_ago"],
                    "qoq_pct": pat_qoq[0],
                    "qoq_label": pat_qoq[1],
                    "yoy_pct": pat_yoy[0],
                    "yoy_label": pat_yoy[1],
                },
                "tax_expense": {
                    "current": tax["current"],
                    "previous_quarter": tax["previous_quarter"],
                    "year_ago": tax["year_ago"],
                },
                "pat_total": {
                    "current": pat_total["current"],
                    "previous_quarter": pat_total["previous_quarter"],
                    "year_ago": pat_total["year_ago"],
                },
                "pat_attributable_to_owners": {
                    "current": pat_owners["current"],
                    "previous_quarter": pat_owners["previous_quarter"],
                    "year_ago": pat_owners["year_ago"],
                },
                "share_of_associates_jv": {
                    "current": share_associates["current"],
                    "previous_quarter": share_associates["previous_quarter"],
                    "year_ago": share_associates["year_ago"],
                },
            },
            "associates_after_tax": associates_after_tax,
            "is_lender": is_lender,
            "check": check,
            "check_diff": round(check_diff, 2),
            "page": raw_data.get("page"),
            "source_pdf_url": source_pdf_url,
        },
    }


def find_results_events(lookback_days: int = 45, force: bool = False) -> list[dict[str, Any]]:
    """Group results filings from the last lookback_days into 3-hour event clusters."""
    client = get_client()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff = (now_utc - datetime.timedelta(days=lookback_days)).isoformat()

    res = (
        client.table("filings")
        .select("*")
        .eq("category", "results")
        .gte("filed_at", cutoff)
        .order("filed_at", desc=True)
        .execute()
    )
    filings = res.data or []

    # Cluster by ticker within 3 hours
    clusters: list[list[dict[str, Any]]] = []
    for f in filings:
        t = datetime.datetime.fromisoformat(f["filed_at"].replace("Z", "+00:00"))
        matched = False
        for cl in clusters:
            if cl[0]["ticker"] == f["ticker"]:
                cluster_times = [
                    datetime.datetime.fromisoformat(x["filed_at"].replace("Z", "+00:00"))
                    for x in cl
                ]
                if any(abs((t - ct).total_seconds()) <= 10800 for ct in cluster_times):
                    cl.append(f)
                    matched = True
                    break
        if not matched:
            clusters.append([f])

    # For each cluster, pick the main filing
    pending_events = []
    for cl in clusters:
        # Check if any filing in this cluster already has enrichment.results (skip unless force=True)
        if not force and any((f.get("enrichment") or {}).get("results") for f in cl):
            continue

        # Choose the best main filing: prefer Outcome of Board Meeting
        def rank(f: dict[str, Any]) -> int:
            subj = (f.get("subject") or "").lower()
            if "outcome of board meeting" in subj:
                return 1
            if "financial result" in subj or "results" in subj:
                return 2
            return 3

        sorted_cl = sorted(cl, key=rank)
        pending_events.append(sorted_cl[0])

    logger.info("Found %d pending results events needing enrichment in last %d days (force=%s).", len(pending_events), lookback_days, force)
    return pending_events


def get_event_filings(ticker: str, filed_at_str: str) -> list[dict[str, Any]]:
    """Retrieve all filings for the ticker within 3 hours of the results filing."""
    client = get_client()
    filed_at = datetime.datetime.fromisoformat(filed_at_str.replace("Z", "+00:00"))
    start = (filed_at - datetime.timedelta(hours=3)).isoformat()
    end = (filed_at + datetime.timedelta(hours=3)).isoformat()

    res = (
        client.table("filings")
        .select("*")
        .eq("ticker", ticker)
        .gte("filed_at", start)
        .lte("filed_at", end)
        .order("filed_at", desc=True)
        .execute()
    )
    return res.data or []


def prioritize_filing_pdfs(filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioritize PDFs likely to contain quarterly financial results."""
    def score(f: dict[str, Any]) -> int:
        subj = (f.get("subject") or "").lower()
        if "outcome of board meeting" in subj:
            return 1
        if "financial result" in subj or "results" in subj:
            return 2
        if "financial statement" in subj or "quick results" in subj:
            return 3
        return 4

    valid = [f for f in filings if f.get("attachment_url")]
    return sorted(valid, key=score)


def enrich_results_event(main_filing: dict[str, Any], prompt_template: str) -> dict[str, Any] | None:
    """Enrich a single results event by finding the results PDF and extracting numbers."""
    ticker = main_filing["ticker"]
    filing_id = main_filing["id"]
    filed_at = main_filing["filed_at"]

    event_filings = get_event_filings(ticker, filed_at)
    candidate_filings = prioritize_filing_pdfs(event_filings)

    logger.info("[%s] Testing %d candidate PDF(s) for results filing %s", ticker, len(candidate_filings), filing_id)

    for cand in candidate_filings:
        url = cand["attachment_url"]
        subj = cand.get("subject", "")
        logger.info("[%s] Downloading and testing PDF (%s): %s", ticker, subj, url)
        try:
            pdf_bytes = download_pdf(url)
            trimmed_bytes = trim_pdf_pages(pdf_bytes, max_pages=15)
            extracted = call_json(
                task="reasoning",
                prompt=prompt_template,
                prompt_version="v2",
                pdf_bytes=trimmed_bytes,
            )

            if isinstance(extracted, dict) and extracted.get("found") is True:
                logger.info("[%s] Results statement found on page %s (%s)", ticker, extracted.get("page"), extracted.get("basis"))
                processed = process_results_data(extracted, url)

                # Persist to database
                client = get_client()
                enr = main_filing.get("enrichment") or {}
                enr["results"] = processed["results"]

                client.table("filings").update({
                    "summary": processed["headline"],
                    "enrichment": enr,
                }).eq("id", filing_id).execute()

                return {
                    "ticker": ticker,
                    "id": filing_id,
                    "headline": processed["headline"],
                    **processed["results"],
                }
            else:
                logger.info("[%s] No results statement found in this PDF.", ticker)
        except Exception as exc:
            logger.error("[%s] Error processing PDF %s: %s", ticker, url, exc)

    logger.warning("[%s] Could not extract results statement from any candidate PDF.", ticker)
    return None


def run_pipeline(force: bool = False) -> list[dict[str, Any]]:
    """Execute the results enrichment pipeline across all pending results filings."""
    prompt_template = load_prompt_template()
    pending = find_results_events(lookback_days=45, force=force)
    processed_records: list[dict[str, Any]] = []

    for f in pending:
        try:
            record = enrich_results_event(f, prompt_template)
            if record:
                processed_records.append(record)
        except Exception as exc:
            logger.error("Failed processing results for %s (%s): %s", f.get("ticker"), f.get("id"), exc)

    return processed_records


def print_summary_table(records: list[dict[str, Any]]) -> None:
    """Print clean human-readable summary table comparing processed records against known figures."""
    print("\n" + "=" * 115)
    print("FINN FINANCIAL RESULTS ENRICHMENT SUMMARY (v2)")
    print("=" * 115)

    headers = (
        f"{'Ticker':<10} {'Basis':<12} {'Rev (₹cr)':<10} {'EBITDA':<10} {'PBT':<10} "
        f"{'PAT (₹cr)':<10} {'Rev YoY':<10} {'PAT YoY':<12} {'Check':<7} {'Headline'}"
    )
    print(headers)
    print("-" * 115)

    by_ticker: dict[str, dict[str, Any]] = {}
    for r in records:
        ticker = r["ticker"]
        by_ticker[ticker] = r
        basis = r.get("basis", "")
        m = r.get("metrics") or {}
        rev = m.get("revenue", {}).get("current")
        rev_str = f"{rev:.1f}" if rev is not None else "-"
        ebitda = m.get("ebitda", {}).get("current")
        ebitda_str = f"{ebitda:.1f}" if ebitda is not None else ("(lender)" if r.get("is_lender") else "-")
        pbt = m.get("pbt", {}).get("current")
        pbt_str = f"{pbt:.1f}" if pbt is not None else "-"
        pat = m.get("pat", {}).get("current")
        pat_str = f"{pat:.1f}" if pat is not None else "-"

        rev_yoy = m.get("revenue", {}).get("yoy_pct")
        rev_lbl = m.get("revenue", {}).get("yoy_label")
        rev_yoy_str = f"{rev_yoy:+.1f}%" if rev_yoy is not None else (rev_lbl or "-")

        pat_yoy = m.get("pat", {}).get("yoy_pct")
        pat_lbl = m.get("pat", {}).get("yoy_label")
        pat_yoy_str = f"{pat_yoy:+.1f}%" if pat_yoy is not None else (pat_lbl or "-")

        check = "OK" if r.get("check") else "FAIL"
        headline = r.get("headline", "")

        print(
            f"{ticker:<10} {basis:<12} {rev_str:<10} {ebitda_str:<10} {pbt_str:<10} "
            f"{pat_str:<10} {rev_yoy_str:<10} {pat_yoy_str:<12} {check:<7} {headline}"
        )

    print("-" * 115)
    print("\nSPECIFIC REQUESTED VERIFICATIONS:")

    # 1. Cipla's PAT
    if "CIPLA" in by_ticker:
        c = by_ticker["CIPLA"]
        cm = c.get("metrics", {})
        c_pat = cm.get("pat", {}).get("current")
        c_tot = cm.get("pat_total", {}).get("current")
        c_own = cm.get("pat_attributable_to_owners", {}).get("current")
        print(f"  • CIPLA PAT: Displayed={c_pat} cr (Attributable={c_own} cr, Total={c_tot} cr, YoY={cm.get('pat', {}).get('yoy_pct')}%)")

    # 2. Check results for HUL, MAZDOCK, TATACONSUM
    for t in ["HINDUNILVR", "MAZDOCK", "TATACONSUM"]:
        if t in by_ticker:
            item = by_ticker[t]
            im = item.get("metrics", {})
            pbt_val = im.get("pbt", {}).get("current")
            tax_val = im.get("tax_expense", {}).get("current") if "tax_expense" in im else None
            tot_pat = im.get("pat_total", {}).get("current")
            assoc = im.get("share_of_associates_jv", {}).get("current")
            check_st = "OK" if item.get("check") else "FAIL"
            diff_st = item.get("check_diff", 0)
            print(f"  • {t:<10} Check: {check_st} (diff: ₹{diff_st} cr, PBT={pbt_val}, Total PAT={tot_pat}, Assoc={assoc})")

    # 3. Nazara's revenue for all three columns with period labels exactly as printed
    if "NAZARA" in by_ticker:
        n = by_ticker["NAZARA"]
        np = n.get("periods", {})
        nm = n.get("metrics", {}).get("revenue", {})
        print("  • NAZARA Revenue Columns (as printed):")
        print(f"      Current          [{np.get('current')}]:           ₹{nm.get('current')} cr")
        print(f"      Previous Quarter [{np.get('previous_quarter')}]:  ₹{nm.get('previous_quarter')} cr")
        print(f"      Year Ago         [{np.get('year_ago')}]:          ₹{nm.get('year_ago')} cr")

    print("=" * 115 + "\n")


if __name__ == "__main__":
    force_run = "--force" in sys.argv or True
    records = run_pipeline(force=force_run)
    print_summary_table(records)
