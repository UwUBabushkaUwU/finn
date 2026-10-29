"""Supabase client and database helper functions for FINN."""

from typing import Any
import time
import logging
from supabase import create_client, Client
from pipeline.config import SUPABASE_URL, SUPABASE_SECRET_KEY

logger = logging.getLogger("db")
_client: Client | None = None


def get_client(force_new: bool = False) -> Client:
    """Return a Supabase client built with SUPABASE_URL and SUPABASE_SECRET_KEY."""
    global _client
    if _client is None or force_new:
        if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
            raise ValueError(
                "Missing SUPABASE_URL or SUPABASE_SECRET_KEY in environment variables."
            )
        _client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    return _client


def upsert(table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str | None = None) -> list[dict[str, Any]]:
    """Upsert one or more rows into the specified table with retry on network failure."""
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return []

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            client = get_client()
            query = client.table(table)
            if on_conflict:
                response = query.upsert(rows, on_conflict=on_conflict).execute()
            else:
                response = query.upsert(rows).execute()
            return response.data or []
        except Exception as exc:
            logger.warning("Database upsert to %s failed (attempt %d/%d): %s", table, attempt, max_retries, exc)
            if attempt == max_retries:
                raise
            get_client(force_new=True)
            time.sleep(1.0 * attempt)
    return []


def select(table: str, **filters: Any) -> list[dict[str, Any]]:
    """Select rows from table with optional exact equality filters with retry on network failure."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            client = get_client()
            query = client.table(table).select("*")
            for key, value in filters.items():
                query = query.eq(key, value)
            response = query.execute()
            return response.data or []
        except Exception as exc:
            logger.warning("Database select from %s failed (attempt %d/%d): %s", table, attempt, max_retries, exc)
            if attempt == max_retries:
                raise
            get_client(force_new=True)
            time.sleep(1.0 * attempt)
    return []
