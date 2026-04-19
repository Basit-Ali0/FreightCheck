# backend/src/freightcheck/api/audit.py
"""POST /audit endpoint per API Contract.

Creates an ``AuditSession`` in Mongo with ``status=processing``, spawns the
LangGraph agent as a FastAPI background task, and returns a 201 immediately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from freightcheck.agent.graph import build_graph, make_initial_state
from freightcheck.errors import DatabaseError, DuplicateAuditError, SessionNotFoundError
from freightcheck.schemas.api import AuditRequest, AuditResponse
from freightcheck.schemas.audit import SessionStatus
from freightcheck.services import upload_cache
from freightcheck.services.session_store import get_mongo_session_store

router = APIRouter(tags=["audit"])
log = structlog.get_logger()


async def _run_agent(session_id: str, raw_texts: dict[str, str]) -> None:
    """Execute the LangGraph agent; write terminal status to Mongo on completion or crash."""
    log.info("agent.started", session_id=session_id)
    store = get_mongo_session_store()
    try:
        graph = build_graph()
        initial_state = make_initial_state(session_id, raw_texts)
        await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}},
        )
    except Exception:
        log.exception(
            "agent.error",
            session_id=session_id,
            error_type="UnhandledAgentError",
            error_message="Agent crashed",
            node_name="run_agent",
        )
        try:
            await store.upsert_checkpoint_async(
                session_id,
                {
                    "status": SessionStatus.FAILED.value,
                    "error_message": "Agent crashed unexpectedly. Check server logs.",
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            log.exception("agent.error_persist_failed", session_id=session_id)


@router.post("/audit", response_model=AuditResponse, status_code=201)
async def trigger_audit(
    body: AuditRequest,
    background_tasks: BackgroundTasks,
) -> AuditResponse | JSONResponse:
    """Trigger the LangGraph agent for a previously uploaded session."""
    session_id = body.session_id

    # 1. Validate session_id exists in upload cache.
    # upload_cache.get raises SessionNotFoundError if absent or expired.
    # API Contract says cache-miss on /audit is 400 (not the global 404).
    try:
        raw_texts = upload_cache.get(session_id)
    except SessionNotFoundError:
        return JSONResponse(
            status_code=400,
            content={
                "error": "SessionNotFoundError",
                "detail": f"No upload found for session_id '{session_id}'. "
                "Upload documents first via POST /upload.",
            },
        )

    # 2. Atomically create the initial session document (unique ``session_id`` index).
    store = get_mongo_session_store()
    created_at = datetime.now(UTC)
    initial_doc: dict[str, Any] = {
        "session_id": session_id,
        "status": SessionStatus.PROCESSING.value,
        "created_at": created_at.isoformat(),
        "completed_at": None,
        "error_message": None,
        "extracted_fields": {},
        "extraction_confidence": {},
        "exceptions": [],
        "report": None,
        "tool_calls": [],
        "planner_decisions": [],
        "iteration_count": 0,
        "needs_human_review": False,
        "review_reasons": [],
        "tokens_used": 0,
        "elapsed_ms": 0,
    }
    try:
        await store.create_audit_session_if_absent(session_id, initial_doc)
    except DuplicateAuditError:
        raise
    except DatabaseError:
        raise
    except Exception as exc:
        log.exception("mongo.error", session_id=session_id, operation="create_audit_session")
        raise DatabaseError(
            "Failed to create audit session. Please try again.",
            session_id=session_id,
        ) from exc

    # 3. Remove from upload cache — the agent now owns the raw texts.
    upload_cache.delete(session_id)

    # 4. Spawn the agent as a background task.
    background_tasks.add_task(_run_agent, session_id, raw_texts)

    return AuditResponse(
        session_id=session_id,
        status=SessionStatus.PROCESSING,
        message=f"Audit started. Poll /sessions/{session_id} for results.",
        created_at=created_at,
    )
