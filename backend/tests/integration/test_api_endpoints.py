# backend/tests/integration/test_api_endpoints.py
"""Integration tests for M5 API endpoints.

Uses an in-memory ``FakeSessionStore`` that replaces the real Mongo-backed
session store, so no live MongoDB or Gemini key is required. Tests cover:
- POST /audit (happy path, cache miss, duplicate)
- GET /sessions (list, empty)
- GET /sessions/:id (found, not found)
- GET /sessions/:id/trajectory (found, not found)
- GET /health
- CORS (allowed + disallowed origins)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from freightcheck.errors import DuplicateAuditError
from freightcheck.main import app
from freightcheck.services import upload_cache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = doc.tobytes()
    doc.close()
    return bytes(buf)


def _three_valid_pdfs() -> dict[str, tuple[str, bytes, str]]:
    return {
        "bol": ("bol.pdf", _make_text_pdf("Bill of Lading MSKU1234567"), "application/pdf"),
        "invoice": (
            "invoice.pdf",
            _make_text_pdf("Commercial Invoice INV-2026-0042"),
            "application/pdf",
        ),
        "packing_list": (
            "packing_list.pdf",
            _make_text_pdf("Packing List 50 packages"),
            "application/pdf",
        ),
    }


def _sample_completed_session(session_id: str = "test-session-1") -> dict[str, Any]:
    """Return a realistic completed session document."""
    return {
        "session_id": session_id,
        "status": "complete",
        "created_at": "2026-04-18T10:30:00Z",
        "completed_at": "2026-04-18T10:30:22Z",
        "error_message": None,
        "extracted_fields": {"bol": {"incoterm": "CIF"}, "invoice": {"incoterm": "CIF"}},
        "extraction_confidence": {
            "bol": {"incoterm": {"field": "incoterm", "value": "CIF",
                                 "confidence": 0.98, "rationale": None}},
        },
        "exceptions": [],
        "report": {
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "passed_count": 3,
            "summary": "No discrepancies found.",
        },
        "tool_calls": [
            {
                "tool_call_id": "tc-0001",
                "iteration": 1,
                "tool_name": "validate_field_match",
                "args": {"field": "incoterm", "doc_a": "bol", "doc_b": "invoice",
                         "tolerance": 0.0},
                "result": {"status": "match"},
                "started_at": "2026-04-18T10:30:15.120Z",
                "completed_at": "2026-04-18T10:30:15.140Z",
                "duration_ms": 20,
                "status": "success",
                "error": None,
            },
        ],
        "planner_decisions": [
            {
                "iteration": 1,
                "chosen_tools": ["validate_field_match"],
                "rationale": "Check incoterm match.",
                "terminate": False,
                "created_at": "2026-04-18T10:30:15.100Z",
            },
        ],
        "iteration_count": 1,
        "needs_human_review": False,
        "review_reasons": [],
        "tokens_used": 5000,
        "elapsed_ms": 22100,
    }


# ---------------------------------------------------------------------------
# In-memory session store that replaces the real Mongo-backed one.
# ---------------------------------------------------------------------------


class FakeSessionStore:
    """Dict-backed stand-in for ``MongoSessionStore``."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def ensure_indexes(self) -> None:
        pass

    async def create_audit_session_if_absent(
        self, session_id: str, doc: dict[str, Any]
    ) -> None:
        """Atomically reject duplicate ``session_id`` (mirrors Mongo unique index)."""
        if session_id in self._data:
            raise DuplicateAuditError(
                f"An audit has already been triggered for session_id '{session_id}'. "
                "Poll /sessions/:id for results.",
                session_id=session_id,
            )
        row = {**doc, "session_id": session_id}
        if "created_at" not in row:
            row["created_at"] = datetime.now(UTC).isoformat()
        self._data[session_id] = row

    async def upsert_checkpoint_async(
        self, session_id: str, doc: dict[str, Any]
    ) -> None:
        existing = self._data.get(session_id, {})
        existing.update(doc)
        existing["session_id"] = session_id
        if "created_at" not in existing:
            existing["created_at"] = doc.get(
                "created_at", datetime.now(UTC).isoformat()
            )
        self._data[session_id] = existing

    def upsert_checkpoint(self, session_id: str, doc: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.upsert_checkpoint_async(session_id, doc))
            return
        task = loop.create_task(self.upsert_checkpoint_async(session_id, doc))
        task.add_done_callback(lambda _: None)  # prevent GC

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        doc = self._data.get(session_id)
        return dict(doc) if doc else None

    async def list_sessions(self) -> list[dict[str, Any]]:
        docs = sorted(
            self._data.values(), key=lambda d: d.get("created_at", ""), reverse=True
        )
        return [dict(d) for d in docs]

    async def ping(self) -> bool:
        return True

    def seed(self, doc: dict[str, Any]) -> None:
        """Pre-load a session document for read-path tests."""
        sid = doc["session_id"]
        self._data[sid] = dict(doc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_store() -> FakeSessionStore:
    return FakeSessionStore()


@pytest.fixture
async def client(fake_store: FakeSessionStore) -> AsyncIterator[AsyncClient]:
    with patch(
        "freightcheck.services.session_store.get_mongo_session_store",
        return_value=fake_store,
    ), patch(
        "freightcheck.api.audit.get_mongo_session_store",
        return_value=fake_store,
    ), patch(
        "freightcheck.api.sessions.get_mongo_session_store",
        return_value=fake_store,
    ), patch(
        "freightcheck.api.health.get_mongo_session_store",
        return_value=fake_store,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _upload_and_get_session_id(client: AsyncClient) -> str:
    """Upload three PDFs and return the ``session_id``."""
    files = _three_valid_pdfs()
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 200
    return str(resp.json()["session_id"])


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mongo"] in {"connected", "disconnected"}
    assert body["gemini"] in {"configured", "not_configured"}


# ---------------------------------------------------------------------------
# POST /audit
# ---------------------------------------------------------------------------


async def test_audit_happy_path(
    client: AsyncClient, fake_store: FakeSessionStore
) -> None:
    session_id = await _upload_and_get_session_id(client)

    # Mock the agent so it doesn't actually run Gemini
    with patch(
        "freightcheck.api.audit._run_agent", new_callable=AsyncMock
    ):
        resp = await client.post("/audit", json={"session_id": session_id})

    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["status"] == "processing"
    assert "created_at" in body
    assert session_id in body["message"]

    # Verify initial doc was written to the fake store.
    doc = await fake_store.get_session(session_id)
    assert doc is not None
    assert doc["status"] == "processing"


async def test_audit_cache_miss_returns_400(client: AsyncClient) -> None:
    resp = await client.post(
        "/audit", json={"session_id": "nonexistent-session-id"}
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "SessionNotFoundError"
    assert "Upload documents first" in body["detail"]


async def test_audit_duplicate_returns_400(
    client: AsyncClient, fake_store: FakeSessionStore
) -> None:
    session_id = await _upload_and_get_session_id(client)

    # Pre-populate the store to simulate a previous audit
    fake_store.seed({"session_id": session_id, "status": "complete"})
    assert len(fake_store._data) == 1

    resp = await client.post("/audit", json={"session_id": session_id})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "DuplicateAuditError"
    assert session_id in body["detail"]
    # Upload cache must not be cleared when creation is rejected (API Contract order).
    assert upload_cache.get(session_id) is not None
    assert len(fake_store._data) == 1, "duplicate /audit must not insert a second session row"


async def test_openapi_get_session_detail_refs_audit_session_schema(
    client: AsyncClient,
) -> None:
    """``GET /sessions/{{id}}`` documents the full ``AuditSession`` contract in OpenAPI."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    get_op = spec["paths"]["/sessions/{session_id}"]["get"]
    ref = get_op["responses"]["200"]["content"]["application/json"]["schema"].get(
        "$ref",
        "",
    )
    assert ref.endswith("/AuditSession")
    assert "AuditSession" in spec.get("components", {}).get("schemas", {})


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


async def test_sessions_list_empty(client: AsyncClient) -> None:
    resp = await client.get("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert body["total"] == 0


async def test_sessions_list_returns_seeded_sessions(
    client: AsyncClient, fake_store: FakeSessionStore
) -> None:
    fake_store.seed(_sample_completed_session("sess-1"))
    fake_store.seed(_sample_completed_session("sess-2"))

    resp = await client.get("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["sessions"]) == 2
    # Each summary has the expected fields
    for s in body["sessions"]:
        assert "session_id" in s
        assert "status" in s
        assert "created_at" in s
        assert "iteration_count" in s


# ---------------------------------------------------------------------------
# GET /sessions/:id
# ---------------------------------------------------------------------------


async def test_session_detail_found(
    client: AsyncClient, fake_store: FakeSessionStore
) -> None:
    doc = _sample_completed_session("detail-1")
    fake_store.seed(doc)

    resp = await client.get("/sessions/detail-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "detail-1"
    assert body["status"] == "complete"
    assert body["report"]["critical_count"] == 0
    assert len(body["tool_calls"]) == 1
    assert len(body["planner_decisions"]) == 1
    assert "extracted_fields" in body


async def test_session_detail_not_found(client: AsyncClient) -> None:
    resp = await client.get("/sessions/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "SessionNotFoundError"


# ---------------------------------------------------------------------------
# GET /sessions/:id/trajectory
# ---------------------------------------------------------------------------


async def test_trajectory_found(
    client: AsyncClient, fake_store: FakeSessionStore
) -> None:
    doc = _sample_completed_session("traj-1")
    fake_store.seed(doc)

    resp = await client.get("/sessions/traj-1/trajectory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "traj-1"
    assert body["status"] == "complete"
    assert body["iteration_count"] == 1
    assert len(body["tool_calls"]) == 1
    assert len(body["planner_decisions"]) == 1
    assert body["tokens_used"] == 5000
    # Trajectory should NOT include extracted_fields
    assert "extracted_fields" not in body


async def test_trajectory_not_found(client: AsyncClient) -> None:
    resp = await client.get("/sessions/does-not-exist/trajectory")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "SessionNotFoundError"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


async def test_cors_allowed_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_cors_disallowed_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORSMiddleware does not set allow-origin for disallowed origins.
    assert resp.headers.get("access-control-allow-origin") is None
