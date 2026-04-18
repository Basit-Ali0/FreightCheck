# backend/src/freightcheck/schemas/agent.py
"""Agent trajectory and audit-session persistence models per Data Models spec section 1.4."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from freightcheck.schemas.audit import AuditReport, ExceptionRecord, SessionStatus
from freightcheck.schemas.documents import ExtractionConfidence


class ToolCall(BaseModel):
    """A single invocation of a tool by the agent, captured in the trajectory."""

    tool_call_id: str
    iteration: int
    tool_name: str
    args: dict[str, Any]
    result: Any
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: Literal["success", "error"]
    error: str | None = None


class PlannerDecision(BaseModel):
    """What the planner chose at a given iteration and why."""

    iteration: int
    chosen_tools: list[str]
    rationale: str
    terminate: bool
    created_at: datetime


class AuditSession(BaseModel):
    """Top-level MongoDB document model representing a complete audit session."""

    session_id: str
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None

    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    extraction_confidence: dict[str, dict[str, ExtractionConfidence]] = Field(
        default_factory=dict,
    )
    exceptions: list[ExceptionRecord] = Field(default_factory=list)
    report: AuditReport | None = None

    tool_calls: list[ToolCall] = Field(default_factory=list)
    planner_decisions: list[PlannerDecision] = Field(default_factory=list)
    iteration_count: int = 0
    needs_human_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    tokens_used: int = 0
    elapsed_ms: int = 0
