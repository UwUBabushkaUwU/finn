"""Alerts generation pipeline for FINN.

Generates alerts for portfolio companies (in_portfolio = true) based on:
1. Unusual price moves (|pct_change| >= price_move_pct)
2. Unusual volume spikes (vol_ratio >= volume_multiple)
3. Material filings (priority 1, within last 48 hours, in alert_categories)

Thresholds are dynamically read from the settings table (row 1).
Alerts are upserted on (ticker, kind, trigger_date, filing_id) for idempotency.
"""

from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import logging
import datetime

# Fix Windows console encoding for non-ASCII characters (e.g. ₹ and ×)
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

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("alerts")

# Suppress verbose HTTP logs from supabase / httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def load_settings() -> dict[str, Any]:
    """Load alert thresholds and categories from settings table (id = 1)."""
    client = get_client()
    res = client.table("settings").select("*").eq("id", 1).execute()
    if not res.data:
        raise ValueError("Settings row (id = 1) not found in settings table.")
    settings = res.data[0]
    logger.info(
        "Loaded settings: price_move_pct=%.1f%%, volume_multiple=%.1fx, lookback=%d days, alert_categories=%s",
        float(settings.get("price_move_pct", 5.0)),
        float(settings.get("volume_multiple", 2.0)),
        int(settings.get("volume_lookback_days", 20)),
        settings.get("alert_categories", []),
    )
    return settings


def get_portfolio_tickers() -> set[str]:
    """Retrieve tickers of companies currently in the portfolio (in_portfolio = true)."""
    companies = select("companies", in_portfolio=True)
    tickers = {c["ticker"] for c in companies if "ticker" in c}
    return tickers


def delete_non_portfolio_alerts(portfolio_tickers: set[str]) -> int:
    """Delete any existing alerts in the database for non-portfolio companies."""
    client = get_client()
    res = client.table("alerts").select("id, ticker").execute()
    rows = res.data or []
    ids_to_delete = [r["id"] for r in rows if r.get("ticker") not in portfolio_tickers]
    if ids_to_delete:
        logger.info(
            "Found %d alerts for non-portfolio companies to delete: IDs %s",
            len(ids_to_delete),
            ids_to_delete,
        )
        client.table("alerts").delete().in_("id", ids_to_delete).execute()
    return len(ids_to_delete)


def get_latest_prices(portfolio_tickers: set[str]) -> list[dict[str, Any]]:
    """Retrieve the latest price row for each portfolio company."""
    if not portfolio_tickers:
        logger.warning("No portfolio companies provided.")
        return []

    client = get_client()
    # Fetch recent prices ordered by date desc to find the latest row per ticker
    res = client.table("prices").select("*").order("date", desc=True).limit(500).execute()
    latest_by_ticker: dict[str, dict[str, Any]] = {}
    for row in res.data or []:
        t = row.get("ticker")
        if t in portfolio_tickers and t not in latest_by_ticker:
            latest_by_ticker[t] = row

    # Fallback: if any portfolio ticker was not in the top 500 rows, query it directly
    for t in portfolio_tickers:
        if t not in latest_by_ticker:
            indiv = client.table("prices").select("*").eq("ticker", t).order("date", desc=True).limit(1).execute()
            if indiv.data:
                latest_by_ticker[t] = indiv.data[0]

    logger.info(
        "Found latest price rows for %d / %d portfolio companies.",
        len(latest_by_ticker),
        len(portfolio_tickers),
    )
    return list(latest_by_ticker.values())


def build_price_and_volume_alerts(
    latest_prices: list[dict[str, Any]], settings: dict[str, Any]
) -> list[dict[str, Any]]:
    """Generate price_move and volume_spike alert candidates from latest price rows."""
    price_move_pct = float(settings.get("price_move_pct", 5.0))
    volume_multiple = float(settings.get("volume_multiple", 2.0))
    lookback_days = int(settings.get("volume_lookback_days", 20))

    alerts: list[dict[str, Any]] = []

    for row in latest_prices:
        ticker = row.get("ticker")
        date_str = str(row.get("date"))
        pct_change = row.get("pct_change")
        vol_ratio = row.get("vol_ratio")

        if not ticker or not date_str:
            continue

        # Check price move alert: |pct_change| >= price_move_pct
        if pct_change is not None and abs(pct_change) >= price_move_pct:
            direction = "Up" if pct_change >= 0 else "Down"
            msg = f"{direction} {abs(pct_change):.1f}% today"
            alerts.append({
                "ticker": ticker,
                "kind": "price_move",
                "message": msg,
                "value": round(float(pct_change), 2),
                "threshold": price_move_pct,
                "filing_id": None,
                "trigger_date": date_str,
                "seen": False,
            })

        # Check volume spike alert: vol_ratio >= volume_multiple
        if vol_ratio is not None and vol_ratio >= volume_multiple:
            msg = f"Volume {vol_ratio:.1f}× its {lookback_days}-day average"
            alerts.append({
                "ticker": ticker,
                "kind": "volume_spike",
                "message": msg,
                "value": round(float(vol_ratio), 2),
                "threshold": volume_multiple,
                "filing_id": None,
                "trigger_date": date_str,
                "seen": False,
            })

    return alerts


def build_material_filing_alerts(
    settings: dict[str, Any], portfolio_tickers: set[str]
) -> list[dict[str, Any]]:
    """Generate material_filing alert candidates for priority 1 filings of portfolio companies in last 48 hours."""
    client = get_client()
    raw_categories = settings.get("alert_categories") or []
    # Case-insensitive category set
    alert_categories_lower = {str(c).strip().lower() for c in raw_categories}

    # Cutoff: 48 hours ago in UTC
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff_utc = (now_utc - datetime.timedelta(hours=48)).isoformat()

    res = (
        client.table("filings")
        .select("id, ticker, category, priority, summary, subject, filed_at")
        .eq("priority", 1)
        .gte("filed_at", cutoff_utc)
        .order("filed_at", desc=True)
        .execute()
    )

    filings = res.data or []
    alerts: list[dict[str, Any]] = []

    for f in filings:
        ticker = f.get("ticker")
        if ticker not in portfolio_tickers:
            continue

        cat = str(f.get("category") or "").strip()
        if cat.lower() not in alert_categories_lower:
            continue

        filed_at_raw = f.get("filed_at")
        if not filed_at_raw:
            continue

        # Parse filed_at timestamp and convert to IST date
        dt_utc = datetime.datetime.fromisoformat(str(filed_at_raw).replace("Z", "+00:00"))
        dt_ist = dt_utc.astimezone(ZoneInfo("Asia/Kolkata"))
        trigger_date = dt_ist.date().isoformat()

        # Headline message: summary with fallback to subject
        headline = (f.get("summary") or f.get("subject") or "Material announcement").strip()

        alerts.append({
            "ticker": ticker,
            "kind": "material_filing",
            "message": headline,
            "value": None,
            "threshold": None,
            "filing_id": str(f["id"]),
            "trigger_date": trigger_date,
            "seen": False,
        })

    logger.info(
        "Found %d priority 1 material filings in last 48h for portfolio companies matching alert categories.",
        len(alerts),
    )
    return alerts


def sync_alerts(candidate_alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """Check existing alerts, upsert candidate alerts, and return summary counts."""
    client = get_client()

    # Deduplicate candidates by unique key: (ticker, kind, trigger_date, filing_id)
    unique_candidates: dict[tuple, dict[str, Any]] = {}
    for a in candidate_alerts:
        key = (a["ticker"], a["kind"], a["trigger_date"], a.get("filing_id"))
        unique_candidates[key] = a

    candidates = list(unique_candidates.values())

    # Query existing alerts to distinguish new vs already present
    res = client.table("alerts").select("ticker, kind, trigger_date, filing_id").execute()
    existing_rows = res.data or []
    existing_keys = {
        (r["ticker"], r["kind"], str(r["trigger_date"]), r.get("filing_id"))
        for r in existing_rows
    }

    kinds = ["price_move", "volume_spike", "material_filing"]
    summary_by_kind = {k: {"created": 0, "already_present": 0} for k in kinds}

    for a in candidates:
        kind = a["kind"]
        key = (a["ticker"], kind, a["trigger_date"], a.get("filing_id"))
        if key in existing_keys:
            summary_by_kind[kind]["already_present"] += 1
        else:
            summary_by_kind[kind]["created"] += 1

    # Perform upsert
    if candidates:
        logger.info("Upserting %d alerts into alerts table...", len(candidates))
        upsert("alerts", candidates, on_conflict="ticker,kind,trigger_date,filing_id")
    else:
        logger.info("No candidate alerts to upsert.")

    return {
        "by_kind": summary_by_kind,
        "total_candidates": len(candidates),
        "total_created": sum(v["created"] for v in summary_by_kind.values()),
        "total_already_present": sum(v["already_present"] for v in summary_by_kind.values()),
    }


def print_summary_and_today(sync_result: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    """Print human-readable summary of alerts created vs present and list today's alerts."""
    today_ist = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    by_kind = sync_result["by_kind"]

    print("\n" + "=" * 55)
    print("                 ALERTS SUMMARY")
    print("=" * 55)
    print(f"{'Alert Kind':<18} | {'Created':<10} | {'Already Present':<15}")
    print("-" * 55)
    for kind in ["price_move", "volume_spike", "material_filing"]:
        stats = by_kind.get(kind, {"created": 0, "already_present": 0})
        print(f"{kind:<18} | {stats['created']:<10} | {stats['already_present']:<15}")
    print("-" * 55)
    print(
        f"{'TOTAL':<18} | {sync_result['total_created']:<10} | {sync_result['total_already_present']:<15}"
    )
    print("=" * 55 + "\n")

    # Filter today's alerts
    today_alerts = [a for a in candidates if a["trigger_date"] == today_ist]

    print("=" * 55)
    print(f"       TODAY'S ALERTS ({today_ist} IST) - {len(today_alerts)} Total")
    print("=" * 55)
    if not today_alerts:
        print("  No alerts triggered for today.")
    else:
        for idx, alert in enumerate(today_alerts, start=1):
            kind_badge = f"[{alert['kind']}]"
            print(f"{idx:2d}. {alert['ticker']:<10} {kind_badge:<17} {alert['message']}")
    print("=" * 55 + "\n")


def generate_alerts() -> None:
    """Main workflow to generate price, volume, and material filing alerts."""
    logger.info("Starting alerts generation pipeline...")
    settings = load_settings()
    portfolio_tickers = get_portfolio_tickers()
    logger.info("Identified %d portfolio companies (in_portfolio = true).", len(portfolio_tickers))

    # Clean up any non-portfolio alerts
    deleted_count = delete_non_portfolio_alerts(portfolio_tickers)
    if deleted_count > 0:
        logger.info("Removed %d legacy alerts for non-portfolio companies.", deleted_count)

    # 1. Price and volume alerts (portfolio only)
    latest_prices = get_latest_prices(portfolio_tickers)
    pv_alerts = build_price_and_volume_alerts(latest_prices, settings)
    logger.info("Generated %d price & volume candidate alerts.", len(pv_alerts))

    # 2. Material filing alerts (portfolio only)
    filing_alerts = build_material_filing_alerts(settings, portfolio_tickers)
    logger.info("Generated %d material filing candidate alerts.", len(filing_alerts))

    all_candidates = pv_alerts + filing_alerts

    # 3. Upsert and calculate summary
    sync_result = sync_alerts(all_candidates)

    # 4. Print summary and today's alerts
    print_summary_and_today(sync_result, all_candidates)


def main() -> None:
    """CLI entrypoint."""
    try:
        generate_alerts()
    except Exception as exc:
        logger.error("Alerts pipeline encountered a fatal error: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
