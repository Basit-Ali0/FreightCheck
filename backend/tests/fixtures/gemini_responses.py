# backend/tests/fixtures/gemini_responses.py
"""Reusable Gemini response builders for unit tests.

Per Testing Spec §5: "Reusable response builders live in
tests/fixtures/gemini_responses.py (e.g. good_bol_extraction(),
low_confidence_bol_extraction())."

These return raw JSON strings that match the response_schema of each prompt,
so tests can monkeypatch `_raw_gemini_call` to return them without touching
the Google SDK.
"""

from __future__ import annotations

import json
from typing import Any


def good_semantic_response(
    status: str = "match",
    reason: str = "Values refer to the same entity.",
) -> str:
    """Valid response matching the `_SemanticResponse` schema."""
    return json.dumps({"status": status, "reason": reason})


def malformed_semantic_response() -> str:
    """Response that will fail schema validation (missing `reason`)."""
    return json.dumps({"status": "match"})


def good_reextraction_response(
    value: Any = "CIF",
    confidence: float = 0.95,
    rationale: str | None = None,
) -> str:
    """Valid response matching ``ReExtractStringResult`` (string field re-extraction)."""
    return json.dumps(
        {"value": value, "confidence": confidence, "rationale": rationale},
    )


def empty_response() -> str:
    """Blank string — provokes the worst-case schema failure."""
    return ""
