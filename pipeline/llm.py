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

_fallback_active: dict[str, bool] = {}
_client_text: genai.Client | None = None
_client_pdf: genai.Client | None = None


def get_gemini_client(has_pdf: bool = False) -> genai.Client:
    """Return a Google GenAI client (90s timeout for PDF calls, 20s for text-only)."""
    global _client_text, _client_pdf
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in environment variables.")
    if has_pdf:
        if _client_pdf is None:
            # HttpOptions timeout is in milliseconds: 90 seconds = 90,000 ms
            _client_pdf = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=90_000),
            )
        return _client_pdf
    else:
        if _client_text is None:
            # HttpOptions timeout is in milliseconds: 25 seconds = 25,000 ms
            _client_text = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=25_000),
            )
        return _client_text


def compute_cache_key(
    model: str, prompt_version: str, prompt: str, pdf_bytes: bytes | None = None
) -> str:
    """Compute sha256(model + prompt_version + prompt + sha256(pdf_bytes))."""
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else ""
    raw = f"{model}{prompt_version}{prompt}{pdf_hash}"
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


def _execute_gemini_call(
    model: str,
    prompt: str,
    pdf_bytes: bytes | None = None,
    fast_fail_503: bool = False,
) -> dict[str, Any] | list[Any]:
    """Execute Gemini generate_content with JSON mode and rate-limit backoff."""
    client = get_gemini_client(has_pdf=bool(pdf_bytes))
    backoff_delays = [10, 30, 60]

    contents: list[Any] | str
    if pdf_bytes:
        pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        contents = [pdf_part, prompt]
    else:
        contents = prompt

    for attempt, delay in enumerate(backoff_delays, start=1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            text = (response.text or "").strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                cleaned = re.sub(r",\s*([\]}])", r"\1", text)
                return json.loads(cleaned)
        except Exception as exc:
            err_msg = str(exc).lower()
            is_503 = (
                "503" in err_msg
                or "unavailable" in err_msg
                or "high demand" in err_msg
                or "504" in err_msg
                or "deadline" in err_msg
                or "timeout" in err_msg
                or "resource_exhausted" in err_msg
                or "quota" in err_msg
            )
            if fast_fail_503 and is_503:
                logger.warning("Fast-failing to fallback on %s: %s", model, exc)
                raise exc

            # Check for rate-limiting, temporary spikes, JSON formatting glitches, or server issues
            is_rate_limit = (
                "429" in err_msg
                or "resource_exhausted" in err_msg
                or "quota" in err_msg
                or "rate" in err_msg
                or is_503
                or "504" in err_msg
                or "deadline" in err_msg
                or "timeout" in err_msg
                or "temporar" in err_msg
                or "json" in err_msg
                or "decode" in err_msg
                or "expecting property" in err_msg
            )
            if is_rate_limit and attempt <= len(backoff_delays):
                _stats["retries"] += 1
                logger.warning(
                    "Retryable error calling %s (attempt %d/%d). Waiting %ds before retry: %s",
                    model,
                    attempt,
                    len(backoff_delays),
                    delay,
                    exc,
                )
                time.sleep(delay)
            else:
                logger.error("Gemini call failed on attempt %d: %s", attempt, exc)
                raise exc

    raise RuntimeError(f"Exhausted retries calling model {model}")


def call_json(
    task: str,
    prompt: str,
    prompt_version: str,
    pdf_bytes: bytes | None = None,
    use_cache: bool = True,
) -> dict[str, Any] | list[Any]:
    """Execute a structured JSON LLM call with caching and rate-limit backoff.

    Args:
        task: "bulk" or "reasoning" (picks model from pipeline.config.MODEL_IDS).
        prompt: Full prompt string.
        prompt_version: Version tag (e.g. "v1") included in cache key.
        pdf_bytes: Optional raw PDF file bytes to send as an application/pdf part.
        use_cache: Whether to check llm_cache before executing.

    Returns:
        Parsed dict or list from the model JSON response.
    """
    model = MODEL_IDS.get(task)
    if not model:
        raise ValueError(f"Unknown LLM task '{task}'. Valid tasks: {list(MODEL_IDS.keys())}")

    cache_key = compute_cache_key(model, prompt_version, prompt, pdf_bytes=pdf_bytes)

    if use_cache:
        cached_output = check_cache(cache_key)
        if cached_output is not None:
            _stats["cache_hits"] += 1
            return cached_output

    bulk_model = MODEL_IDS.get("bulk")
    if use_cache and task == "reasoning" and _fallback_active.get("reasoning") and bulk_model and bulk_model != model:
        logger.warning(
            "Reasoning model %s is currently experiencing high demand (503). Using bulk fallback %s...",
            model,
            bulk_model,
        )
        fallback_key = compute_cache_key(bulk_model, prompt_version, prompt, pdf_bytes=pdf_bytes)
        fallback_cached = check_cache(fallback_key)
        if fallback_cached is not None:
            logger.warning("Fallback used: loaded cached response from bulk model %s", bulk_model)
            save_cache(cache_key, task, bulk_model, fallback_cached)
            _stats["cache_hits"] += 1
            return fallback_cached
        output = _execute_gemini_call(bulk_model, prompt, pdf_bytes=pdf_bytes)
        logger.warning("Fallback used: executed live Gemini call with bulk model %s", bulk_model)
        save_cache(fallback_key, task, bulk_model, output)
        save_cache(cache_key, task, bulk_model, output)
        return output

    # Call model live
    _stats["real_calls"] += 1
    try:
        output = _execute_gemini_call(
            model,
            prompt,
            pdf_bytes=pdf_bytes,
            fast_fail_503=(task == "reasoning" and bulk_model is not None and bulk_model != model),
        )
        save_cache(cache_key, task, model, output)
        return output
    except Exception as exc:
        if task == "reasoning" and bulk_model and bulk_model != model:
            _fallback_active["reasoning"] = True
            logger.warning(
                "Reasoning model %s failed with error: %s. Falling back to bulk model %s.",
                model,
                exc,
                bulk_model,
            )
            fallback_key = compute_cache_key(bulk_model, prompt_version, prompt, pdf_bytes=pdf_bytes)
            if use_cache:
                fallback_cached = check_cache(fallback_key)
                if fallback_cached is not None:
                    logger.warning(
                        "Fallback used: loaded cached response from bulk model %s for reasoning task",
                        bulk_model,
                    )
                    save_cache(cache_key, task, bulk_model, fallback_cached)
                    _stats["cache_hits"] += 1
                    return fallback_cached

            output = _execute_gemini_call(bulk_model, prompt, pdf_bytes=pdf_bytes)
            logger.warning("Fallback used: executed live Gemini call with bulk model %s", bulk_model)
            save_cache(cache_key, task, bulk_model, output)
            save_cache(fallback_key, task, bulk_model, output)
            return output
        raise exc


def get_cache_stats() -> dict[str, int]:
    """Return a copy of the current LLM run statistics."""
    return dict(_stats)


def reset_cache_stats() -> None:
    """Reset the LLM run statistics."""
    _stats["cache_hits"] = 0
    _stats["real_calls"] = 0
    _stats["retries"] = 0
