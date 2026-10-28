"""Seed script to populate initial companies and alert settings in Supabase.

Safe to run repeatedly (idempotent).
"""

import sys
import logging
from pipeline.config import PORTFOLIO, RESEARCH, ALERT_DEFAULTS
from pipeline.db import upsert, select

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")


def seed_companies() -> int:
    """Upsert all portfolio and research companies from portfolio.yaml into Supabase."""
    company_rows = []

    for item in PORTFOLIO:
        company_rows.append({
            "ticker": item["ticker"],
            "name": item.get("name", item["ticker"]),
            "sector": item.get("sector"),
            "size": item.get("size"),
            "in_portfolio": True,
            "is_research": False,
        })

    for item in RESEARCH:
        company_rows.append({
            "ticker": item["ticker"],
            "name": item.get("name", item["ticker"]),
            "sector": item.get("sector"),
            "size": item.get("size"),  # None for research set if not specified
            "in_portfolio": False,
            "is_research": True,
        })

    upsert("companies", company_rows, on_conflict="ticker")
    return len(company_rows)


def seed_settings() -> None:
    """Upsert default alert configuration into row 1 of settings."""
    settings_row = {
        "id": 1,
        "volume_multiple": float(ALERT_DEFAULTS.get("volume_multiple", 2.0)),
        "volume_lookback_days": int(ALERT_DEFAULTS.get("volume_lookback_days", 20)),
        "price_move_pct": float(ALERT_DEFAULTS.get("price_move_pct", 5.0)),
        "digest_window_hours": float(ALERT_DEFAULTS.get("digest_window_hours", 24.0)),
        "alert_categories": list(ALERT_DEFAULTS.get("alert_categories", [])),
    }

    upsert("settings", [settings_row], on_conflict="id")


def main() -> None:
    """Execute seed and output table row counts."""
    logger.info("Starting database seed...")
    try:
        count = seed_companies()
        logger.info("Upserted %d companies from portfolio.yaml", count)

        seed_settings()
        logger.info("Upserted alert defaults into settings (id=1)")

        companies = select("companies")
        settings = select("settings")

        print("\n--- Seed Complete ---")
        print(f"companies row count: {len(companies)}")
        print(f"settings row count : {len(settings)}")
        print("---------------------\n")

    except Exception as e:
        logger.error("Seeding failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
