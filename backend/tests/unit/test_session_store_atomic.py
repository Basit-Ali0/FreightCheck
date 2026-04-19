# backend/tests/unit/test_session_store_atomic.py
"""MongoSessionStore atomic create semantics for ``POST /audit``."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError

from freightcheck.errors import DatabaseError, DuplicateAuditError
from freightcheck.services.session_store import MongoSessionStore


def _bare_store() -> MongoSessionStore:
    """``MongoSessionStore`` without opening a real Motor client."""
    return object.__new__(MongoSessionStore)


def _minimal_initial_doc(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "status": "processing",
        "created_at": "2026-04-19T12:00:00+00:00",
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


@pytest.mark.asyncio
async def test_create_audit_session_if_absent_first_insert_succeeds() -> None:
    store = _bare_store()
    store._indexes_ready = True
    coll = MagicMock()
    coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    store._sessions = coll

    await store.create_audit_session_if_absent("sid-1", _minimal_initial_doc("sid-1"))
    coll.insert_one.assert_awaited_once()
    call_kw = coll.insert_one.await_args[0][0]
    assert call_kw["session_id"] == "sid-1"
    assert call_kw["status"] == "processing"
    assert "updated_at" in call_kw


@pytest.mark.asyncio
async def test_create_audit_session_if_absent_duplicate_key_is_duplicate_audit_error() -> None:
    store = _bare_store()
    store._indexes_ready = True
    coll = MagicMock()
    coll.insert_one = AsyncMock(
        side_effect=DuplicateKeyError("E11000 duplicate key error", code=11000),
    )
    store._sessions = coll

    with pytest.raises(DuplicateAuditError, match="already been triggered"):
        await store.create_audit_session_if_absent("sid-dup", _minimal_initial_doc("sid-dup"))


@pytest.mark.asyncio
async def test_create_audit_session_if_absent_other_pymongo_error_is_database_error() -> None:
    store = _bare_store()
    store._indexes_ready = True
    coll = MagicMock()
    coll.insert_one = AsyncMock(side_effect=PyMongoError("network"))
    store._sessions = coll

    with pytest.raises(DatabaseError, match="Failed to create audit session"):
        await store.create_audit_session_if_absent("sid-db", _minimal_initial_doc("sid-db"))
