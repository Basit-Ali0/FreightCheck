# backend/src/freightcheck/api/sessions.py
"""Session query endpoints per API Contract.

- GET /sessions          — list all sessions sorted by created_at desc
- GET /sessions/:id      — full session detail (primary polling endpoint)
- GET /sessions/:id/trajectory — lightweight trajectory-only response
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from freightcheck.errors import SessionNotFoundError
from freightcheck.schemas.agent import AuditSession
from freightcheck.schemas.api import SessionListResponse, SessionSummary, TrajectoryResponse
from freightcheck.schemas.audit import SessionStatus
from freightcheck.services.session_store import get_mongo_session_store

router = APIRouter(tags=["sessions"])


def _to_session_summary(doc: dict[str, Any]) -> SessionSummary:
    """Project a raw Mongo document to the ``SessionSummary`` list-item shape."""
    status = doc.get("status", SessionStatus.PROCESSING.value)
    report = doc.get("report")
    is_terminal = status in {
        SessionStatus.COMPLETE.value,
        SessionStatus.AWAITING_REVIEW.value,
    }
    return SessionSummary(
        session_id=doc["session_id"],
        status=SessionStatus(status),
        created_at=doc["created_at"],
        completed_at=doc.get("completed_at"),
        critical_count=report["critical_count"] if is_terminal and report else None,
        warning_count=report["warning_count"] if is_terminal and report else None,
        info_count=report["info_count"] if is_terminal and report else None,
        needs_human_review=doc.get("needs_human_review", False),
        iteration_count=doc.get("iteration_count", 0),
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    """Return all audit sessions ordered by ``created_at`` descending."""
    store = get_mongo_session_store()
    docs = await store.list_sessions()
    summaries = [_to_session_summary(d) for d in docs]
    return SessionListResponse(sessions=summaries, total=len(summaries))


@router.get("/sessions/{session_id}", response_model=AuditSession)
async def get_session(session_id: str) -> AuditSession:
    """Return the full detail of a single audit session."""
    store = get_mongo_session_store()
    doc = await store.get_session(session_id)
    if doc is None:
        raise SessionNotFoundError(
            f"No session found with id '{session_id}'",
            session_id=session_id,
        )
    # Strip non-contract fields before validating the wire shape.
    doc.pop("_id", None)
    doc.pop("updated_at", None)
    return AuditSession.model_validate(doc)


@router.get("/sessions/{session_id}/trajectory", response_model=TrajectoryResponse)
async def get_trajectory(session_id: str) -> TrajectoryResponse:
    """Return the agent trajectory without the heavier extracted-fields payload."""
    store = get_mongo_session_store()
    doc = await store.get_session(session_id)
    if doc is None:
        raise SessionNotFoundError(
            f"No session found with id '{session_id}'",
            session_id=session_id,
        )
    return TrajectoryResponse(
        session_id=doc["session_id"],
        status=SessionStatus(doc.get("status", SessionStatus.PROCESSING.value)),
        iteration_count=doc.get("iteration_count", 0),
        planner_decisions=doc.get("planner_decisions", []),
        tool_calls=doc.get("tool_calls", []),
        tokens_used=doc.get("tokens_used", 0),
        elapsed_ms=doc.get("elapsed_ms", 0),
    )
