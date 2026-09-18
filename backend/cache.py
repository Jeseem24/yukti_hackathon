"""
cache.py — Simple JSON file-based cache for generated LLM insights.

Persists across server restarts. Explanations are never regenerated once cached.
This prevents wasted API calls and protects against rate limits / wifi issues
during a hackathon demo.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent / "insights_cache.json"
_lock = Lock()


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Cache file unreadable ({e}), starting fresh.")
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to write cache: {e}")


def get_cached(event_id: str) -> Optional[Tuple[str, str]]:
    """
    Return (explanation, recommendation) for event_id if cached, else None.
    """
    cache = _load_cache()
    entry = cache.get(event_id)
    if entry:
        logger.debug(f"Cache hit: {event_id}")
        return entry["explanation"], entry["recommendation"]
    return None


def set_cached(event_id: str, explanation: str, recommendation: str) -> None:
    """
    Store (explanation, recommendation) for event_id in persistent cache.
    Thread-safe via Lock.
    """
    with _lock:
        cache = _load_cache()
        cache[event_id] = {
            "explanation": explanation,
            "recommendation": recommendation,
        }
        _save_cache(cache)
        logger.debug(f"Cached insight for: {event_id}")


def clear_cache() -> None:
    """Utility — clear all cached insights (dev/testing use)."""
    with _lock:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        logger.info("Insight cache cleared.")
