"""Gemini 2.5 Flash USD estimate (Evaluation harness only; easy to update)."""

from __future__ import annotations

# Published-style blended rate per 1M tokens (input+output averaged for harness).
# Update when switching models or pricing tiers.
USD_PER_MILLION_TOKENS = 0.35


def estimate_cost_usd(tokens: int) -> float:
    return round((tokens / 1_000_000.0) * USD_PER_MILLION_TOKENS, 6)
