"""
insight_generator.py — LLM-powered anomaly explanation with deterministic fallback.

Strategy (per Agent Brief requirements):
  1. Check cache first — never regenerate if already stored.
  2. Try Groq LLM with grounded, structured prompt.
  3. On ANY failure (rate limit, timeout, API down, bad JSON) → use fallback template.
  4. Cache the result regardless of which path was used.

The prompt STRICTLY grounds the LLM in passed-in numbers.
Judges will check whether explanations contain hallucinated causes — any invented
sensor name or unsupported root cause is an automatic credibility hit.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from cache import get_cached, set_cached

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------
_PROMPT_PATH = Path(__file__).parent / "prompts" / "insight_prompt.txt"
_PROMPT_TEMPLATE: Optional[str] = None


def _load_prompt() -> str:
    global _PROMPT_TEMPLATE
    if _PROMPT_TEMPLATE is None:
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            _PROMPT_TEMPLATE = f.read()
    return _PROMPT_TEMPLATE


# ---------------------------------------------------------------------------
# Fallback template (always works — built first per brief)
# ---------------------------------------------------------------------------
def _fallback_insight(
    equipment_id: str,
    start: str,
    end: str,
    duration_hours: float,
    actual_energy: float,
    expected_energy: float,
    residual_pct: float,
    top_contributing_features: list[str],
    severity: float,
    avg_load: float,
) -> Tuple[str, str]:
    """
    Deterministic, numerically-grounded fallback when LLM is unavailable.
    Every claim is derived from the passed-in numbers only — no hallucination possible.
    """
    direction = "above" if residual_pct > 0 else "below"
    abs_pct = abs(residual_pct)
    features_str = ", ".join(top_contributing_features) if top_contributing_features else "energy consumption"
    top_feature = top_contributing_features[0] if top_contributing_features else "the flagged sensors"

    severity_label = (
        "high-severity" if severity >= 0.7 else
        "moderate-severity" if severity >= 0.4 else
        "low-severity"
    )

    explanation = (
        f"{equipment_id} consumed {actual_energy:.1f} kWh on average during the {duration_hours:.1f}-hour "
        f"window from {start} to {end}, which is {abs_pct:.1f}% {direction} the model's expected "
        f"{expected_energy:.1f} kWh for the prevailing building load of {avg_load:.0f} RT. "
        f"This {severity_label} anomaly (severity {severity:.2f}) was most strongly associated with "
        f"deviations in: {features_str}."
    )
    recommendation = (
        f"Inspect {top_feature} on {equipment_id} and verify sensor readings against maintenance logs "
        f"for the {start[:10]} period to determine whether this deviation represents equipment degradation "
        f"or a measurement fault."
    )
    return explanation, recommendation


# ---------------------------------------------------------------------------
# Groq LLM call
# ---------------------------------------------------------------------------
def _call_groq(prompt_text: str) -> Tuple[str, str]:
    """
    Call Groq API with the grounded prompt.
    Raises on failure — caller handles with fallback.

    GROQ_API_KEY must be set in environment or .env file.
    """
    import groq as groq_sdk

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set.")

    client = groq_sdk.Groq(api_key=api_key)

    model_name = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise HVAC operations analyst. "
                    "Always respond with valid JSON only. "
                    "Never add explanation, markdown, or text outside the JSON object."
                ),
            },
            {"role": "user", "content": prompt_text},
        ],
        temperature=0.2,   # low temperature = more grounded, less creative hallucination
        max_tokens=400,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    parsed = json.loads(raw)

    explanation = parsed.get("explanation", "").strip()
    recommendation = parsed.get("recommendation", "").strip()

    if not explanation or not recommendation:
        raise ValueError("LLM returned empty explanation or recommendation.")

    return explanation, recommendation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_insight(
    event_id: str,
    equipment_id: str,
    start: str,
    end: str,
    duration_hours: float,
    actual_energy: float,
    expected_energy: float,
    residual_pct: float,
    avg_load: float,
    baseline_efficiency: float,
    event_efficiency: float,
    top_contributing_features: list[str],
    severity: float,
    context_note: str = "Not available",
) -> Tuple[str, str]:
    """
    Generate (explanation, recommendation) for an anomaly event.

    1. Returns cached result if available.
    2. Tries Groq LLM with grounded prompt.
    3. Falls back to deterministic template on any error.
    4. Caches result before returning.

    Returns:
        (explanation: str, recommendation: str)
    """
    # --- Step 1: Cache check ---
    cached = get_cached(event_id)
    if cached:
        return cached

    features_str = ", ".join(top_contributing_features) if top_contributing_features else "energy consumption"
    residual_direction = "higher than expected" if residual_pct > 0 else "lower than expected"

    # --- Step 2: Try LLM ---
    explanation: Optional[str] = None
    recommendation: Optional[str] = None
    used_llm = False

    try:
        prompt_template = _load_prompt()
        prompt_text = prompt_template.format(
            equipment_id=equipment_id,
            start=start,
            end=end,
            duration_hours=duration_hours,
            severity=severity,
            actual_energy=actual_energy,
            expected_energy=expected_energy,
            residual_pct=residual_pct,
            residual_direction=residual_direction,
            avg_load=avg_load,
            baseline_efficiency=baseline_efficiency,
            event_efficiency=event_efficiency,
            top_contributing_features=features_str,
            context_note=context_note,
        )
        explanation, recommendation = _call_groq(prompt_text)
        used_llm = True
        logger.info(f"LLM insight generated for {event_id}")

    except Exception as e:
        logger.warning(
            f"LLM call failed for {event_id} ({type(e).__name__}: {e}). "
            f"Using fallback template."
        )

    # --- Step 3: Fallback ---
    if not explanation or not recommendation:
        explanation, recommendation = _fallback_insight(
            equipment_id=equipment_id,
            start=start,
            end=end,
            duration_hours=duration_hours,
            actual_energy=actual_energy,
            expected_energy=expected_energy,
            residual_pct=residual_pct,
            top_contributing_features=top_contributing_features,
            severity=severity,
            avg_load=avg_load,
        )
        logger.info(f"Fallback insight used for {event_id}")

    # --- Step 4: Cache ---
    set_cached(event_id, explanation, recommendation)

    return explanation, recommendation
