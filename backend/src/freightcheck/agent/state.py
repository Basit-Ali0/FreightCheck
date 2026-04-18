# backend/src/freightcheck/agent/state.py
"""LangGraph `AgentState` TypedDict per Data Models spec section 2."""

from typing import Any, Literal, TypedDict


class AgentState(TypedDict):
    """State object passed through every LangGraph node.

    Nodes must return a partial dict rather than mutating state. All Pydantic
    models are serialised to dicts before storage in state for JSON
    compatibility. The `error` field is checked at the start of every node;
    when set the node routes to `compile_report` for graceful shutdown.
    """

    session_id: str
    raw_texts: dict[str, str]

    extracted_fields: dict[str, Any]
    extraction_confidence: dict[str, dict[str, dict[str, Any]]]

    plan: list[str]
    tool_calls: list[dict[str, Any]]
    planner_decisions: list[dict[str, Any]]
    iteration_count: int

    validations: list[dict[str, Any]]
    exceptions: list[dict[str, Any]]

    report: dict[str, Any] | None
    needs_human_review: bool
    review_reasons: list[str]

    tokens_used: int
    elapsed_ms: int
    error: str | None

    status: Literal["processing", "complete", "failed", "awaiting_review"]
