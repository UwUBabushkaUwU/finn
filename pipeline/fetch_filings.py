"""Fetch corporate announcements from NSE and store them in Supabase.

Polls the NSE corporate-announcements API for portfolio companies,
maps the announcement fields to the `filings` table, and upserts them idempotently.
"""

from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import os
import time
import hashlib
import argparse
import datetime
import logging
import requests

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import PORTFOLIO_TICKERS, ALL_TICKERS
from pipeline.db import get_client, upsert

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fetch_filings")

# Suppress verbose HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class NSESessionManager:
    """Manages browser-like session with NSE, cookie priming, and retries."""

    NSE_COOKIE_URL = "https://www.nseindia.com/option-chain"
    BASE_API_URL = "https://www.nseindia.com/api/corporate-announcements"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) "
                "Gecko/20100101 Firefox/118.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
        })
        self.prime_cookies()

    def prime_cookies(self) -> None:
        """Visit an NSE page to acquire session and anti-bot cookies."""
        try:
            resp = self.session.get(self.NSE_COOKIE_URL, timeout=15)
            logger.info("Primed NSE session cookies (status: %d)", resp.status_code)
            self.session.headers.update({
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings/announcements",
            })
        except Exception as exc:
            logger.warning("Cookie priming request failed: %s", exc)

    def fetch_announcements(
        self, ticker: str, from_date: str, to_date: str
    ) -> tuple[list[dict[str, Any]] | None, int]:
        """Fetch announcement list for a given ticker and date window."""
        url = f"{self.BASE_API_URL}?index=equities&symbol={ticker}&from_date={from_date}&to_date={to_date}"
        max_retries = 3
        refreshed_cookies = False

        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if isinstance(data, list):
                            return data, 200
                        return [], 200
                    except Exception as json_err:
                        logger.warning("Failed to parse JSON for %s: %s", ticker, json_err)
                        return None, 200
                elif resp.status_code in (401, 403) and not refreshed_cookies:
                    logger.warning(
                        "Received HTTP %d for %s. Refreshing session cookies and retrying...",
                        resp.status_code,
                        ticker,
                    )
                    self.prime_cookies()
                    refreshed_cookies = True
                    time.sleep(1.0)
                    continue
                else:
                    logger.warning(
                        "HTTP %d fetching %s (attempt %d/%d)",
                        resp.status_code,
                        ticker,
                        attempt,
                        max_retries,
                    )
                    if attempt == max_retries:
                        return None, resp.status_code
            except Exception as exc:
                logger.warning(
                    "Error fetching %s (attempt %d/%d): %s",
                    ticker,
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt == max_retries:
                    return None, 0

            time.sleep(attempt * 1.5)

        return None, 0


def parse_ist_to_utc_iso(item: dict[str, Any]) -> str:
    """Parse announcement date/time in IST and convert to UTC ISO 8601 string."""
    sort_date = item.get("sort_date")
    an_dt = item.get("an_dt")
    dt: datetime.datetime | None = None

    if sort_date:
        try:
            dt = datetime.datetime.strptime(str(sort_date).strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    if dt is None and an_dt:
        try:
            dt = datetime.datetime.strptime(str(an_dt).strip(), "%d-%b-%Y %H:%M:%S")
        except ValueError:
            pass

    if dt is None:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    dt_ist = dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    dt_utc = dt_ist.astimezone(datetime.timezone.utc)
    return dt_utc.isoformat()


def compute_filing_id(ticker: str, item: dict[str, Any], filed_at_utc: str, subject: str) -> str:
    """Generate a stable id using NSE's seq_id or a SHA-256 fallback."""
    seq_id = item.get("seq_id")
    if seq_id is not None and str(seq_id).strip():
        return str(seq_id).strip()

    raw_key = f"{ticker}:{filed_at_utc}:{subject}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def format_attachment_url(url: Any) -> str | None:
    """Format and normalize the attachment PDF URL."""
    if not url:
        return None
    url_str = str(url).strip()
    if not url_str:
        return None
    if url_str.startswith("http://") or url_str.startswith("https://"):
        return url_str
    if url_str.startswith("/"):
        return f"https://nsearchives.nseindia.com{url_str}"
    return f"https://nsearchives.nseindia.com/{url_str}"


def map_announcement_to_filing(ticker: str, item: dict[str, Any]) -> dict[str, Any]:
    """Map raw NSE announcement dict to filings table columns."""
    filed_at = parse_ist_to_utc_iso(item)

    desc = (item.get("desc") or "").strip()
    attchmnt_text = (item.get("attchmntText") or "").strip()

    # Subject is the broad topic/headline; Description is full text
    subject = desc if desc else (attchmnt_text if attchmnt_text else "Corporate Announcement")
    description = attchmnt_text if attchmnt_text else (desc if desc else None)

    filing_id = compute_filing_id(ticker, item, filed_at, subject)
    attachment_url = format_attachment_url(item.get("attchmntFile"))

    return {
        "id": filing_id,
        "ticker": ticker,
        "exchange": "NSE",
        "filed_at": filed_at,
        "subject": subject,
        "description": description,
        "attachment_url": attachment_url,
        "raw": item,
        "category": None,
        "priority": None,
        "summary": None,
        "enrichment": None,
    }


def get_existing_filing_ids(ids: list[str]) -> set[str]:
    """Query Supabase to identify which filing ids already exist in DB."""
    if not ids:
        return set()

    client = get_client()
    existing: set[str] = set()
    batch_size = 100

    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        res = client.table("filings").select("id").in_("id", batch).execute()
        for row in res.data or []:
            existing.add(row["id"])

    return existing


def save_filings(filings: list[dict[str, Any]], batch_size: int = 100) -> tuple[int, int]:
    """Upsert filings into Supabase, returning (count_new, count_already_present)."""
    if not filings:
        return 0, 0

    all_ids = [f["id"] for f in filings]
    existing_ids = get_existing_filing_ids(all_ids)

    count_already_present = sum(1 for fid in all_ids if fid in existing_ids)
    count_new = len(all_ids) - count_already_present

    for i in range(0, len(filings), batch_size):
        batch = filings[i : i + batch_size]
        upsert("filings", batch, on_conflict="id")

    return count_new, count_already_present


def fetch_and_store_filings(
    days: int = 7,
    ticker: str | None = None,
    all_tickers: bool = False,
) -> dict[str, Any]:
    """Main pipeline job: download, map, and upsert filings from NSE."""
    if ticker:
        target_tickers = [ticker.strip().upper()]
    elif all_tickers:
        target_tickers = ALL_TICKERS
    else:
        target_tickers = PORTFOLIO_TICKERS

    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=days)
    from_date_str = start_date.strftime("%d-%m-%Y")
    to_date_str = today.strftime("%d-%m-%Y")

    logger.info(
        "Fetching NSE filings for %d ticker(s) from %s to %s (%d days)...",
        len(target_tickers),
        from_date_str,
        to_date_str,
        days,
    )

    session_mgr = NSESessionManager()

    filings_per_ticker: dict[str, int] = {}
    failed_tickers: dict[str, str] = {}
    all_filing_rows: list[dict[str, Any]] = []

    for idx, sym in enumerate(target_tickers):
        items, status = session_mgr.fetch_announcements(sym, from_date_str, to_date_str)
        if items is None:
            failed_tickers[sym] = f"HTTP {status}"
            filings_per_ticker[sym] = 0
            logger.error("Failed to fetch filings for %s (status: %d)", sym, status)
        else:
            filings_per_ticker[sym] = len(items)
            for item in items:
                row = map_announcement_to_filing(sym, item)
                all_filing_rows.append(row)

        # Be polite: pause at least 1 second between symbols
        if idx < len(target_tickers) - 1:
            time.sleep(1.0)

    count_new, count_existing = save_filings(all_filing_rows)

    summary = {
        "tickers_count": len(target_tickers),
        "filings_per_ticker": filings_per_ticker,
        "total_filings_found": len(all_filing_rows),
        "new_filings": count_new,
        "already_present": count_existing,
        "failed_tickers": failed_tickers,
    }

    print("\n================ NSE Filings Summary ================")
    print(f"Tickers processed : {len(target_tickers)}")
    print(f"Total filings     : {summary['total_filings_found']}")
    print(f"New filings       : {summary['new_filings']}")
    print(f"Already present   : {summary['already_present']}")
    print("\nFilings per ticker:")
    for sym, count in filings_per_ticker.items():
        print(f"  {sym:12}: {count}")

    if failed_tickers:
        print("\nFailed tickers:")
        for sym, reason in failed_tickers.items():
            print(f"  {sym:12}: {reason}")
    else:
        print("\nFailed tickers    : None (All succeeded)")
    print("====================================================\n")

    if len(failed_tickers) == len(target_tickers) and len(target_tickers) > 0:
        logger.error("All tickers failed to fetch filings.")
        sys.exit(1)

    return summary


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Fetch corporate announcements from NSE into Supabase.")
    parser.add_argument("--days", type=int, default=7, help="Number of calendar days of history (default: 7)")
    parser.add_argument("--ticker", type=str, default=None, help="Specific NSE symbol to fetch (e.g. LT)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch for all tickers (portfolio + research) instead of only portfolio",
    )
    args = parser.parse_args()

    fetch_and_store_filings(days=args.days, ticker=args.ticker, all_tickers=args.all)


if __name__ == "__main__":
    main()
