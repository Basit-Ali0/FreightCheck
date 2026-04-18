# backend/src/freightcheck/schemas/api.py
"""API request and response models per Data Models spec section 1.5."""

from datetime import datetime

from pydantic import BaseModel, Field

from freightcheck.schemas.agent import PlannerDecision, ToolCall
from freightcheck.schemas.audit import SessionStatus


class UploadResponse(BaseModel):
    """Response returned by `POST /upload`."""

    session_id: str
    message: str
    documents_received: list[str]
    raw_text_lengths: dict[str, int]


class AuditRequest(BaseModel):
    """Request body for `POST /audit`."""

    session_id: str


class AuditResponse(BaseModel):
    """Response returned by `POST /audit`."""

    session_id: str
    status: SessionStatus
    message: str
    created_at: datetime


class SessionSummary(BaseModel):
    """Per-session summary used in the `GET /sessions` list response."""

    session_id: str
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None = None
    critical_count: int | None = None
    warning_count: int | None = None
    info_count: int | None = None
    needs_human_review: bool = False
    iteration_count: int = 0


class SessionListResponse(BaseModel):
    """Response returned by `GET /sessions`."""

    sessions: list[SessionSummary]
    total: int


class TrajectoryResponse(BaseModel):
    """Response returned by `GET /sessions/:id/trajectory`."""

    session_id: str
    status: SessionStatus
    iteration_count: int
    planner_decisions: list[PlannerDecision] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tokens_used: int
    elapsed_ms: int
