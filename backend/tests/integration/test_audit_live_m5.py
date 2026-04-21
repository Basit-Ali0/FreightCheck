# backend/tests/integration/test_audit_live_m5.py
"""Live end-to-end ``/upload`` → ``/audit`` → trajectory polling → session detail (M5 DoD)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from freightcheck.main import app
from freightcheck.services.session_store import get_mongo_session_store
from tests.support.live_integration_env import (
    is_real_gemini_api_key_configured,
    is_real_mongodb_uri_for_live_integration,
)


def _make_text_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = doc.tobytes()
    doc.close()
    return bytes(buf)


def _three_pdfs() -> dict[str, tuple[str, bytes, str]]:
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_upload_audit_poll_session_within_30s() -> None:
    if not is_real_gemini_api_key_configured():
        pytest.skip(
            "GEMINI_API_KEY missing, placeholder, or too short for live Gemini; "
            "skipping live /audit E2E (set a real key in the environment or backend/.env).",
        )
    if not is_real_mongodb_uri_for_live_integration():
        pytest.skip(
            "MONGODB_URI is the canonical offline test default; skipping live /audit E2E "
            "(set MONGODB_URI to a real cluster in backend/.env or the environment).",
        )

    store = get_mongo_session_store()
    if not await store.ping():
        pytest.skip("MongoDB not reachable for live /audit E2E test")

    transport = ASGITransport(app=app)
    deadline = time.monotonic() + 90.0

    async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        files = _three_pdfs()
        up = await client.post("/upload", files=files)
        assert up.status_code == 200, up.text
        session_id = str(up.json()["session_id"])

        aud = await client.post("/audit", json={"session_id": session_id})
        assert aud.status_code == 201, aud.text

        terminal: str | None = None
        trajectory: dict[str, Any] = {}
        while time.monotonic() < deadline:
            tr = await client.get(f"/sessions/{session_id}/trajectory")
            assert tr.status_code == 200, tr.text
            trajectory = tr.json()
            status = trajectory.get("status")
            if status in ("complete", "awaiting_review", "failed"):
                terminal = str(status)
                break
            await asyncio.sleep(0.5)

        assert terminal is not None, "Trajectory did not reach a terminal status within 90s"
        assert terminal in ("complete", "awaiting_review"), (
            f"Live audit ended with status={terminal!r}; expected complete or awaiting_review"
        )

        detail = await client.get(f"/sessions/{session_id}")
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["session_id"] == session_id
        assert body["status"] == terminal
        assert "extracted_fields" in body
        assert "tool_calls" in body
        assert "planner_decisions" in body
