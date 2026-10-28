"""Central LLM client for FINN.

All calls to Google Gemini must pass through this module.
Results are cached in the Supabase llm_cache table, keyed by
sha256(model + prompt_version + prompt).
"""

from typing import Any
from pathlib import Path
import sys
import time
import json
import hashlib
import logging

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google import genai
from google.genai import types
from google.genai.errors import APIError

from pipeline.config import GEMINI_API_KEY, MODEL_IDS
from pipeline.db import get_client, upsert, select

logger = logging.getLogger("llm")

# Global stats for diagnostic logging
_stats = {
    "cache_hits": 0,
    "real_calls": 0,
    "retries": 0,
}

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Return a singleton Google GenAI client."""
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def compute_cache_key(model: str, prompt_version: str, prompt: str) -> str:
    """Compute sha256(model + prompt_version + prompt)."""
    raw = f"{model}{prompt_version}{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_cache(cache_key: str) -> dict[str, Any] | list[Any] | None:
    """Look up a cached LLM response in the llm_cache table."""
    try:
        rows = select("llm_cache", key=cache_key)
        if rows and "output" in rows[0]:
            return rows[0]["output"]
    except Exception as exc:
        logger.warning("Error checking llm_cache: %s", exc)
    return None


def save_cache(cache_key: str, task: str, model: str, output: Any) -> None:
    """Save an LLM response to the llm_cache table."""
    try:
        upsert(
            "llm_cache",
            {
                "key": cache_key,
                "task": task,
                "model": model,
                "output": output,
            },
            on_conflict="key",
        )
    except Exception as exc:
        logger.warning("Error saving to llm_cache: %s", exc)


def _execute_gemini_call(model: str, prompt: str) -> dict[str, Any] | list[Any]:
    """Execute Gemini generate_content with JSON mode and rate-limit backoff."""
    client = get_gemini_client()
    backoff_delays = [10, 30, 60]

    for attempt, delay in enumerate(backoff_delays, start=1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            text = (response.text or "").strip()
            return json.loads(text)
        except Exception as exc:
            # Check for rate-limiting or server quota issues
            err_msg = str(exc).lower()
            is_rate_limit = (
                "429" in err_msg
                or "resource_exhausted" in err_msg
                or "quota" in err_msg
                or "rate" in err_msg
            )
            if is_rate_limit and attempt <= len(backoff_delays):
                _stats["retries"] += 1
                logger.warning(
                    "Rate limit hit calling %s (attempt %d). Waiting %ds before retry...",
                    model,
                    attempt,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error("Gemini call failed on attempt %d: %s", attempt, exc)
                raise exc

    raise RuntimeError(f"Exhausted retries calling model {model}")


def call_json(task: str, prompt: str, prompt_version: str) -> dict[str, Any] | list[Any]:
    """Execute a structured JSON LLM call with caching and rate-limit backoff.

    Args:
        task: "bulk" or "reasoning" (picks model from pipeline.config.MODEL_IDS).
        prompt: Full prompt string.
        prompt_version: Version tag (e.g. "v1") included in cache key.

    Returns:
        Parsed dict or list from the model JSON response.
    """
    model = MODEL_IDS.get(task)
    if not model:
        raise ValueError(f"Unknown LLM task '{task}'. Valid tasks: {list(MODEL_IDS.keys())}")

    cache_key = compute_cache_key(model, prompt_version, prompt)

    cached_output = check_cache(cache_key)
    if cached_output is not None:
        _stats["cache_hits"] += 1
        return cached_output

    # Cache miss: call model
    _stats["real_calls"] += 1
    output = _execute_gemini_call(model, prompt)
    save_cache(cache_key, task, model, output)
    return output


def get_cache_stats() -> dict[str, int]:
    """Return a copy of the current LLM run statistics."""
    return dict(_stats)


def reset_cache_stats() -> None:
    """Reset the LLM run statistics."""
    _stats["cache_hits"] = 0
    _stats["real_calls"] = 0
    _stats["retries"] = 0
