"""Build research corpus for an NSE ticker from screener.in and primary PDFs.

Fetches financial tables and primary documents (concall transcripts, presentations,
and annual reports) for any NSE ticker, parses them into generic structures,
and stores them in Supabase.
"""

from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import os
import io
import time
import re
import hashlib
import argparse
import datetime
import logging
import requests
from bs4 import BeautifulSoup
import pypdf

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.db import get_client, upsert, select

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_corpus")

# Suppress verbose HTTP logs
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("pypdf").setLevel(logging.ERROR)


class ScreenerClient:
    """Manages polite HTTP requests to screener.in and PDF hosts with backoff."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last_request_time: float = 0.0

    def _throttle(self, min_delay: float = 2.0) -> None:
        """Enforce polite interval between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)
        self._last_request_time = time.time()

    def fetch_screener_page(self, ticker: str) -> tuple[str, str]:
        """Fetch company HTML from screener.in.
        
        Tries consolidated first; falls back to standalone if quarterly table is empty.
        Returns (html_text, basis).
        """
        urls = [
            (f"https://www.screener.in/company/{ticker}/consolidated/", "consolidated"),
            (f"https://www.screener.in/company/{ticker}/", "standalone"),
        ]

        for url, basis in urls:
            html = self._get_with_retry(url)
            if not html:
                continue

            # Verify quarterly table has rows
            soup = BeautifulSoup(html, "html.parser")
            quarters_sec = soup.find("section", id="quarters")
            if quarters_sec:
                table = quarters_sec.find("table", class_="data-table")
                if table and table.find("tbody"):
                    rows = table.find("tbody").find_all("tr")
                    if len(rows) > 0:
                        logger.info("Found populated quarterly table for %s using %s", ticker, basis)
                        return html, basis

            logger.info("Quarterly table empty or missing at %s; trying fallback", url)

        # If neither had a populated table but standalone responded, return it
        if html:
            return html, "standalone"
        raise RuntimeError(f"Failed to fetch valid screener page for ticker: {ticker}")

    def download_pdf(self, url: str) -> bytes | None:
        """Download a PDF document politely with retry."""
        self._throttle(min_delay=2.0)
        max_retries = 3
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    return resp.content
                logger.warning("HTTP %d downloading %s (attempt %d/%d)", resp.status_code, url, attempt, max_retries)
            except Exception as exc:
                logger.warning("Error downloading %s (attempt %d/%d): %s", url, attempt, max_retries, exc)

            time.sleep(backoff)
            backoff *= 2.0

        return None

    def _get_with_retry(self, url: str) -> str | None:
        """Fetch URL string with throttling and backoff."""
        self._throttle(min_delay=2.0)
        max_retries = 3
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code == 404:
                    logger.info("URL %s returned 404", url)
                    return None
                logger.warning("HTTP %d fetching %s (attempt %d/%d)", resp.status_code, url, attempt, max_retries)
            except Exception as exc:
                logger.warning("Error fetching %s (attempt %d/%d): %s", url, attempt, max_retries, exc)

            time.sleep(backoff)
            backoff *= 2.0

        return None


def clean_num(val_str: str) -> float | None:
    """Parse table cell text to float or None, stripping commas, %, and formatting."""
    val = val_str.replace(",", "").replace("%", "").strip()
    if not val or val in ("-", "—", "N/A", "NA"):
        return None
    # Handle accounting negative format (e.g. (123.45))
    if val.startswith("(") and val.endswith(")"):
        val = "-" + val[1:-1].strip()
    try:
        return float(val)
    except ValueError:
        return None


def parse_financial_tables(soup: BeautifulSoup) -> dict[str, Any]:
    """Parse all financial tables into generic {columns: [...], rows: [{label, values: [...]}]}.
    
    Handles both corporates and banks/NBFCs without hardcoding row labels.
    """
    section_map = {
        "quarters": "quarterly_results",
        "profit-loss": "profit_loss",
        "balance-sheet": "balance_sheet",
        "cash-flow": "cash_flow",
        "ratios": "ratios",
    }
    tables: dict[str, Any] = {}

    for sec_id, table_key in section_map.items():
        sec = soup.find("section", id=sec_id)
        if not sec:
            continue

        table = sec.find("table", class_="data-table")
        if not table:
            continue

        thead = table.find("thead")
        columns: list[str] = []
        if thead:
            columns = [th.get_text(strip=True) for th in thead.find_all("th") if th.get_text(strip=True)]

        rows: list[dict[str, Any]] = []
        tbody = table.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue

                td0 = tds[0]
                # Remove schedule expander buttons/icons
                for sp in td0.find_all("span", class_="blue-icon"):
                    sp.decompose()
                label = td0.get_text(strip=True).rstrip("+").strip()

                raw_values = [clean_num(td.get_text(strip=True)) for td in tds[1:]]
                # Match values length with columns
                if len(raw_values) < len(columns):
                    raw_values.extend([None] * (len(columns) - len(raw_values)))
                elif len(raw_values) > len(columns):
                    raw_values = raw_values[:len(columns)]

                rows.append({"label": label, "values": raw_values})

        tables[table_key] = {"columns": columns, "rows": rows}

    return tables


def get_discussed_quarter(call_date: datetime.date) -> str:
    """Determine the quarter discussed by a call on call_date.
    
    Rule: a call discusses the most recent quarter that ended before the call date.
    Quarters end on India's April-March fiscal year:
      30 Jun -> Q1
      30 Sep -> Q2
      31 Dec -> Q3
      31 Mar -> Q4
    """
    y = call_date.year
    candidates = [
        (datetime.date(y - 1, 3, 31), "Q4", y - 1),
        (datetime.date(y - 1, 6, 30), "Q1", y),
        (datetime.date(y - 1, 9, 30), "Q2", y),
        (datetime.date(y - 1, 12, 31), "Q3", y),
        (datetime.date(y, 3, 31), "Q4", y),
        (datetime.date(y, 6, 30), "Q1", y + 1),
        (datetime.date(y, 9, 30), "Q2", y + 1),
        (datetime.date(y, 12, 31), "Q3", y + 1),
        (datetime.date(y + 1, 3, 31), "Q4", y + 1),
    ]
    past_ends = [c for c in candidates if c[0] < call_date]
    if not past_ends:
        raise ValueError(f"No past quarter end found for {call_date}")

    last_end = max(past_ends, key=lambda c: c[0])
    q_name, fy_year = last_end[1], last_end[2]
    fy_short = str(fy_year)[-2:]
    return f"{q_name} FY{fy_short}"


def parse_date_string(date_text: str) -> datetime.date | None:
    """Parse date text such as 'Oct 2026' or '23 Oct 2026' into a datetime.date."""
    date_text = date_text.strip()
    month_names = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }

    # Match DD Mon YYYY
    m_full = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", date_text)
    if m_full:
        day = int(m_full.group(1))
        m_str = m_full.group(2).lower()
        year = int(m_full.group(3))
        month = month_names.get(m_str)
        if month:
            return datetime.date(year, month, day)

    # Match Mon YYYY
    m_month = re.search(r"([A-Za-z]+)\s+(\d{4})", date_text)
    if m_month:
        m_str = m_month.group(1).lower()
        year = int(m_month.group(2))
        month = month_names.get(m_str)
        if month:
            # Default to 1st of that month
            return datetime.date(year, month, 1)

    return None


def parse_documents_section(soup: BeautifulSoup) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Parse Concalls and Annual reports from screener.in Documents section.
    
    Returns:
      (concalls_list, latest_annual_report_dict)
    """
    doc_sec = soup.find("section", id="documents")
    if not doc_sec:
        return [], None

    concalls: list[dict[str, Any]] = []
    latest_ar: dict[str, Any] | None = None

    for col in doc_sec.find_all("div", class_="flex-column"):
        heading = col.find(["h2", "h3", "h4"])
        h_text = heading.get_text(strip=True).lower() if heading else ""

        # 1. Concalls
        if "concall" in h_text:
            ul = col.find("ul")
            if not ul:
                continue
            for li in ul.find_all("li", recursive=False):
                # Date label is in first div or text
                d_div = li.find("div")
                d_text = d_div.get_text(strip=True) if d_div else ""
                call_date = parse_date_string(d_text)
                if not call_date:
                    continue

                period = get_discussed_quarter(call_date)

                # Look only for Transcript and PPT links (strictly ignore AI Summary, notes, REC)
                transcript_url: str | None = None
                ppt_url: str | None = None

                for a in li.find_all("a"):
                    link_txt = a.get_text(strip=True).lower()
                    href = a.get("href")
                    if not href:
                        continue
                    if "transcript" in link_txt and not transcript_url:
                        transcript_url = href
                    elif ("ppt" in link_txt or "presentation" in link_txt) and not ppt_url:
                        ppt_url = href

                if transcript_url or ppt_url:
                    concalls.append({
                        "date": call_date,
                        "period": period,
                        "transcript_url": transcript_url,
                        "ppt_url": ppt_url,
                    })

        # 2. Annual reports (most recent only)
        elif "annual" in h_text and not latest_ar:
            ul = col.find("ul")
            if not ul:
                continue
            for li in ul.find_all("li", recursive=False):
                a = li.find("a")
                if not a or not a.get("href"):
                    continue
                a_text = a.get_text(strip=True)
                m_year = re.search(r"(\d{4})", a_text)
                if m_year:
                    year_val = int(m_year.group(1))
                    period_val = f"FY{str(year_val)[-2:]}"
                    event_date_val = datetime.date(year_val, 3, 31)
                    latest_ar = {
                        "url": a.get("href"),
                        "period": period_val,
                        "event_date": event_date_val,
                        "title": a_text,
                    }
                    break

    return concalls, latest_ar


def extract_pdf_pages(pdf_bytes: bytes, max_pages: int = 400) -> tuple[list[str], int, bool]:
    """Extract page text using pypdf, capping at max_pages.
    
    Returns (pages, page_count, text_ok).
    text_ok is False if average characters per page is below 200.
    """
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        cap = min(total_pages, max_pages)
        pages: list[str] = []

        for i in range(cap):
            try:
                page_text = reader.pages[i].extract_text() or ""
            except Exception as exc:
                logger.warning("Error extracting text on page %d: %s", i + 1, exc)
                page_text = ""
            pages.append(page_text)

        page_count = len(pages)
        avg_chars = sum(len(p) for p in pages) / page_count if page_count > 0 else 0
        text_ok = avg_chars >= 200.0
        return pages, page_count, text_ok
    except Exception as exc:
        logger.warning("Failed to parse PDF with pypdf: %s", exc)
        return [], 0, False


def ensure_company_registered(ticker: str, soup: BeautifulSoup) -> None:
    """Ensure the ticker exists in the companies table."""
    try:
        existing = select("companies", ticker=ticker)
        if not existing:
            h1 = soup.find("h1")
            name = h1.get_text(strip=True) if h1 else ticker
            # Clean up screener extra badges in h1 if present
            name = re.sub(r"\s+", " ", name).strip()
            upsert("companies", {
                "ticker": ticker,
                "name": name,
                "in_portfolio": False,
                "is_research": True,
            }, on_conflict="ticker")
            logger.info("Registered new research company in companies table: %s (%s)", ticker, name)
    except Exception as exc:
        logger.warning("Could not register company %s: %s", ticker, exc)


def build_corpus_for_ticker(ticker: str) -> dict[str, Any]:
    """Build research corpus for an NSE symbol and store in Supabase."""
    ticker = ticker.strip().upper()
    client = ScreenerClient()
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. Update research_jobs to running with step 'corpus' (never to 'done')
    try:
        upsert("research_jobs", {
            "ticker": ticker,
            "status": "running",
            "step": "corpus",
            "started_at": now_utc,
            "finished_at": None,
            "error": None,
        }, on_conflict="ticker")
    except Exception as exc:
        logger.warning("Failed to update research_jobs for %s: %s", ticker, exc)

    logger.info("Starting corpus build for %s", ticker)

    try:
        # 2. Fetch screener HTML (consolidated first, fallback to standalone)
        html, basis = client.fetch_screener_page(ticker)
        soup = BeautifulSoup(html, "html.parser")
        ensure_company_registered(ticker, soup)

        # 3. Parse financial tables and upsert into financials
        tables = parse_financial_tables(soup)
        quarterly_cols = tables.get("quarterly_results", {}).get("columns", [])
        upsert("financials", {
            "ticker": ticker,
            "basis": basis,
            "tables": tables,
            "fetched_at": now_utc,
        }, on_conflict="ticker")
        logger.info("Upserted financial tables for %s (basis: %s)", ticker, basis)

        # 4. Parse documents section
        concalls, latest_ar = parse_documents_section(soup)

        # Pick 5 most recent transcripts
        selected_transcripts: list[dict[str, Any]] = []
        for c in concalls:
            if c.get("transcript_url"):
                selected_transcripts.append(c)
                if len(selected_transcripts) == 5:
                    break

        target_quarters = [c["period"] for c in selected_transcripts]

        # Match presentations for those exact target quarters
        selected_ppts: dict[str, dict[str, Any]] = {}
        for c in concalls:
            q = c["period"]
            if q in target_quarters and c.get("ppt_url") and q not in selected_ppts:
                selected_ppts[q] = c

        # Prepare document targets to fetch/verify
        target_docs: list[dict[str, Any]] = []

        # Latest Annual Report
        if latest_ar:
            target_docs.append({
                "kind": "annual_report",
                "period": latest_ar["period"],
                "event_date": latest_ar["event_date"].isoformat(),
                "url": latest_ar["url"],
            })

        # 5 most recent transcripts
        for t in selected_transcripts:
            target_docs.append({
                "kind": "transcript",
                "period": t["period"],
                "event_date": t["date"].isoformat(),
                "url": t["transcript_url"],
            })

        # Presentations for the same quarters
        for q in target_quarters:
            if q in selected_ppts:
                c = selected_ppts[q]
                target_docs.append({
                    "kind": "presentation",
                    "period": q,
                    "event_date": c["date"].isoformat(),
                    "url": c["ppt_url"],
                })

        # 5. Download and extract text for target documents (skip if already in documents)
        documents_summary: list[dict[str, Any]] = []

        for doc in target_docs:
            url = doc["url"]
            doc_id = hashlib.sha256(url.encode("utf-8")).hexdigest()

            # Check if document already exists
            existing_docs = select("documents", id=doc_id)
            if existing_docs:
                row = existing_docs[0]
                logger.info("Document already present: %s %s (%s)", doc["kind"], doc["period"], doc_id[:8])
                documents_summary.append({
                    "kind": row["kind"],
                    "period": row["period"],
                    "page_count": row.get("page_count", 0),
                    "text_ok": row.get("text_ok", False),
                    "url": row["url"],
                    "skipped": True,
                })
                continue

            # Download PDF
            logger.info("Downloading %s for %s (%s)...", doc["kind"], doc["period"], url)
            pdf_bytes = client.download_pdf(url)
            if not pdf_bytes:
                logger.error("Failed to download PDF: %s", url)
                documents_summary.append({
                    "kind": doc["kind"],
                    "period": doc["period"],
                    "page_count": 0,
                    "text_ok": False,
                    "url": url,
                    "error": "Download failed",
                })
                continue

            # Extract pages with pypdf (cap at 400 for annual report or long PDFs)
            pages, page_count, text_ok = extract_pdf_pages(pdf_bytes, max_pages=400)

            # Upsert into documents
            doc_row = {
                "id": doc_id,
                "ticker": ticker,
                "kind": doc["kind"],
                "period": doc["period"],
                "event_date": doc["event_date"],
                "url": url,
                "pages": pages,
                "page_count": page_count,
                "text_ok": text_ok,
                "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            upsert("documents", doc_row, on_conflict="id")
            logger.info("Stored document %s %s: %d pages, text_ok=%s", doc["kind"], doc["period"], page_count, text_ok)

            documents_summary.append({
                "kind": doc["kind"],
                "period": doc["period"],
                "page_count": page_count,
                "text_ok": text_ok,
                "url": url,
                "skipped": False,
            })

        # Notes on missing items
        missing_notes: list[str] = []
        if not latest_ar:
            missing_notes.append("Annual report: not found on screener")
        if len(selected_transcripts) < 5:
            missing_notes.append(f"Transcripts: only {len(selected_transcripts)} found (less than 5 available)")
        for q in target_quarters:
            if q not in selected_ppts:
                missing_notes.append(f"Presentation for {q}: not found on screener")

        summary = {
            "ticker": ticker,
            "basis": basis,
            "quarters": quarterly_cols,
            "documents": documents_summary,
            "missing": missing_notes,
        }

        print_coverage_summary(summary)
        return summary

    except Exception as exc:
        logger.error("Error building corpus for %s: %s", ticker, exc, exc_info=True)
        try:
            upsert("research_jobs", {
                "ticker": ticker,
                "status": "failed",
                "step": "error",
                "error": str(exc),
                "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }, on_conflict="ticker")
        except Exception:
            pass
        raise


def print_coverage_summary(summary: dict[str, Any]) -> None:
    """Format and display human-readable coverage summary."""
    ticker = summary["ticker"]
    basis = summary["basis"]
    quarters = summary["quarters"]
    docs = summary["documents"]
    missing = summary["missing"]

    sep = "=" * 70
    print(f"\n{sep}")
    print(f"COVERAGE SUMMARY: {ticker}")
    print(f"{sep}")
    print(f"Basis used: {basis}")
    print(f"Quarters in quarterly table ({len(quarters)}): {', '.join(quarters)}")
    print(f"\nDocuments found ({len(docs)}):")
    for d in docs:
        status_flag = " (cached)" if d.get("skipped") else ""
        err_flag = f" [ERROR: {d['error']}]" if d.get("error") else ""
        print(f"  - [{d['kind']:<13}] {d['period']:<8}: {d['page_count']:>3} pages, text_ok={str(d['text_ok']):<5}{status_flag}{err_flag}")
        print(f"    URL: {d['url']}")

    if missing:
        print("\nMissing / Notes:")
        for m in missing:
            print(f"  - {m}")
    else:
        print("\nMissing / Notes: None (all requested documents found)")
    print(f"{sep}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research corpus for an NSE ticker.")
    parser.add_argument("--ticker", required=True, help="NSE ticker symbol (e.g. PERSISTENT, TITAN)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_corpus_for_ticker(args.ticker)

