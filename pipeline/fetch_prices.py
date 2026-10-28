"""Fetch daily OHLCV prices from yfinance and store them in Supabase.

Computes pct_change, vol_avg_20, and vol_ratio for each ticker and date.
"""

from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import argparse
import datetime
import logging
import pandas as pd
import numpy as np
import yfinance as yf

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.db import select, upsert

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fetch_prices")

# Suppress verbose HTTP logs from supabase / httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.WARNING)


def filter_completed_trading_days(df: pd.DataFrame) -> pd.DataFrame:
    """Drop today's date from downloaded data if running before 4:00 PM IST.

    Only completed trading days should be saved.
    """
    if df.empty:
        return df

    ist_now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    is_before_4pm = ist_now.time() < datetime.time(16, 0)

    if is_before_4pm:
        today_str = ist_now.date().isoformat()
        mask = [dt.strftime("%Y-%m-%d") != today_str for dt in df.index]
        if not all(mask):
            logger.info(
                "Running before 4:00 PM IST (%s IST). Dropping incomplete trading day %s.",
                ist_now.strftime("%H:%M"),
                today_str,
            )
            df = df[mask]

    return df


def to_python_num(val: Any, target_type: type = float) -> float | int | None:
    """Safely convert numpy/pandas numbers to plain Python float/int or None."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        num = target_type(val)
        if np.isnan(num) or np.isinf(num):
            return None
        return num
    except (ValueError, TypeError):
        return None


def get_all_tickers() -> list[str]:
    """Retrieve all company tickers from the companies table in Supabase."""
    companies = select("companies")
    tickers = [c["ticker"] for c in companies if "ticker" in c]
    return tickers


def download_prices(tickers: list[str], days: int) -> pd.DataFrame:
    """Download daily OHLCV for all tickers using yfinance in one batched call."""
    if not tickers:
        return pd.DataFrame()

    yf_symbols = [f"{ticker}.NS" for ticker in tickers]
    start_date = datetime.date.today() - datetime.timedelta(days=days)
    logger.info(
        "Downloading %d days of data for %d tickers (since %s)...",
        days,
        len(yf_symbols),
        start_date.isoformat(),
    )

    try:
        df = yf.download(
            tickers=yf_symbols,
            start=start_date.isoformat(),
            group_by="ticker",
            progress=False,
            auto_adjust=False,
        )
        return df
    except Exception as exc:
        logger.error("Failed to download price data from yfinance: %s", exc)
        return pd.DataFrame()


def process_ticker_data(ticker: str, df_ticker: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute pct_change, vol_avg_20, and vol_ratio, returning rows ready for upsert."""
    sub = df_ticker.copy()
    if sub.empty or "Close" not in sub.columns:
        return []

    # Drop dates where Close is missing
    sub = sub.dropna(subset=["Close"])
    if sub.empty:
        return []

    # Deduplicate index and sort by date ascending
    sub = sub[~sub.index.duplicated(keep="last")]
    sub = sub.sort_index()

    # pct_change = close vs previous close (%)
    sub["pct_change"] = sub["Close"].pct_change() * 100.0

    # vol_avg_20 = mean volume of previous 20 trading days (excluding current day)
    sub["vol_avg_20"] = sub["Volume"].shift(1).rolling(window=20, min_periods=20).mean()

    # vol_ratio = volume / vol_avg_20
    avg_vol = sub["vol_avg_20"]
    sub["vol_ratio"] = np.where((avg_vol > 0) & avg_vol.notna(), sub["Volume"] / avg_vol, np.nan)

    rows: list[dict[str, Any]] = []
    for dt, row in sub.iterrows():
        date_str = dt.strftime("%Y-%m-%d")
        rows.append({
            "ticker": ticker,
            "date": date_str,
            "open": to_python_num(row.get("Open"), float),
            "high": to_python_num(row.get("High"), float),
            "low": to_python_num(row.get("Low"), float),
            "close": to_python_num(row.get("Close"), float),
            "volume": to_python_num(row.get("Volume"), int),
            "pct_change": to_python_num(row.get("pct_change"), float),
            "vol_avg_20": to_python_num(row.get("vol_avg_20"), float),
            "vol_ratio": to_python_num(row.get("vol_ratio"), float),
        })

    return rows


def save_price_rows(rows: list[dict[str, Any]], batch_size: int = 500) -> int:
    """Upsert price rows into Supabase in batches."""
    if not rows:
        return 0

    total_upserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        upsert("prices", batch, on_conflict="ticker,date")
        total_upserted += len(batch)

    return total_upserted


def fetch_and_store_prices(days: int = 90) -> dict[str, Any]:
    """Main pipeline job: download, compute metrics, and upsert daily prices."""
    tickers = get_all_tickers()
    if not tickers:
        logger.error("No tickers found in companies table.")
        return {
            "tickers_fetched": 0,
            "rows_upserted": 0,
            "tickers_failed": [],
            "latest_date": None,
        }

    raw_df = download_prices(tickers, days=days)
    raw_df = filter_completed_trading_days(raw_df)

    all_rows: list[dict[str, Any]] = []
    tickers_fetched: list[str] = []
    tickers_failed: list[str] = []
    latest_date: str | None = None

    for ticker in tickers:
        yf_symbol = f"{ticker}.NS"
        if raw_df.empty or yf_symbol not in raw_df:
            logger.warning("No data found for ticker %s (%s)", ticker, yf_symbol)
            tickers_failed.append(ticker)
            continue

        ticker_rows = process_ticker_data(ticker, raw_df[yf_symbol])
        if not ticker_rows:
            logger.warning("No valid trading days for ticker %s (%s)", ticker, yf_symbol)
            tickers_failed.append(ticker)
            continue

        tickers_fetched.append(ticker)
        all_rows.extend(ticker_rows)

        # Track latest date seen
        ticker_latest = ticker_rows[-1]["date"]
        if latest_date is None or ticker_latest > latest_date:
            latest_date = ticker_latest

    rows_upserted = save_price_rows(all_rows)

    summary = {
        "tickers_fetched": len(tickers_fetched),
        "rows_upserted": rows_upserted,
        "tickers_failed": tickers_failed,
        "latest_date": latest_date,
    }

    # Print human-readable summary
    print("\n================ EOD Prices Summary ================")
    print(f"Tickers fetched : {summary['tickers_fetched']} / {len(tickers)}")
    print(f"Rows upserted   : {summary['rows_upserted']}")
    print(f"Tickers failed  : {len(summary['tickers_failed'])} {summary['tickers_failed']}")
    print(f"Latest date     : {summary['latest_date']}")
    print("====================================================\n")

    if summary["tickers_fetched"] == 0 and len(tickers) > 0:
        logger.error("All tickers failed to fetch price data.")
        sys.exit(1)

    return summary


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Fetch EOD stock prices from yfinance into Supabase.")
    parser.add_argument("--days", type=int, default=90, help="Number of calendar days of history (default: 90)")
    args = parser.parse_args()

    fetch_and_store_prices(days=args.days)


if __name__ == "__main__":
    main()
