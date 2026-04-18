# backend/src/freightcheck/agent/state.py
"""LangGraph `AgentState` with reducers per LangGraph Flow Spec §6."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


def append_list(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """Additive list reducer: append new items."""
    if left is None:
        return list(right or [])
    if right is None:
        return left
    return left + right


def sum_ints(left: int | None, right: int | None) -> int:
    """Additive int reducer."""
    return int(left or 0) + int(right or 0)


def deep_merge(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge nested dicts (`extracted_fields`, `extraction_confidence`)."""
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    merged = dict(left)
    for key, val in right.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def or_bool(left: bool | None, right: bool | None) -> bool:
    """Logical OR for `needs_human_review` (once True, stays True)."""
    return bool(left) or bool(right)


def keep_first_error(left: str | None, right: str | None) -> str | None:
    """Keep the first non-empty error string."""
    if left:
        return left
    return right


class AgentState(TypedDict):
    """State passed through every LangGraph node (Data Models §2 + Flow Spec §6)."""

    session_id: str
    raw_texts: dict[str, str]

    extracted_fields: Annotated[dict[str, Any], deep_merge]
    extraction_confidence: Annotated[dict[str, dict[str, dict[str, Any]]], deep_merge]

    # FIFO queue: `{"tool_name": str, "args": dict}` (Flow Spec §2.3)
    plan: list[dict[str, Any]]
    tool_calls: Annotated[list[dict[str, Any]], append_list]
    planner_decisions: Annotated[list[dict[str, Any]], append_list]
    iteration_count: Annotated[int, sum_ints]

    validations: Annotated[list[dict[str, Any]], append_list]
    exceptions: Annotated[list[dict[str, Any]], append_list]

    report: dict[str, Any] | None
    needs_human_review: Annotated[bool, or_bool]
    review_reasons: Annotated[list[str], append_list]

    tokens_used: Annotated[int, sum_ints]
    elapsed_ms: Annotated[int, sum_ints]
    error: Annotated[str | None, keep_first_error]

    status: Literal["processing", "complete", "failed", "awaiting_review"]
