# backend/tests/integration/test_upload_endpoint.py
"""Integration tests for `POST /upload` covering happy path and every error case."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient

from freightcheck.main import app
from freightcheck.services import upload_cache
from freightcheck.settings import settings


def _make_text_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = doc.tobytes()
    doc.close()
    return bytes(buf)


def _make_blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
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


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_upload_happy_path(client: AsyncClient) -> None:
    files = _three_valid_pdfs()
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {
        "session_id",
        "message",
        "documents_received",
        "raw_text_lengths",
    }
    assert body["documents_received"] == ["bol", "invoice", "packing_list"]
    assert set(body["raw_text_lengths"].keys()) == {"bol", "invoice", "packing_list"}
    for length in body["raw_text_lengths"].values():
        assert length > 0

    cached = upload_cache.get(body["session_id"])
    assert set(cached.keys()) == {"bol", "invoice", "packing_list"}


async def test_upload_missing_document_returns_400(client: AsyncClient) -> None:
    files = _three_valid_pdfs()
    del files["packing_list"]
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "MissingDocumentError"
    assert "packing_list" in body["detail"]
    assert "Missing:" in body["detail"]


async def test_upload_wrong_file_type_returns_400(client: AsyncClient) -> None:
    files = _three_valid_pdfs()
    files["invoice"] = ("invoice.jpg", b"\xff\xd8\xff\xe0 jpeg bytes", "image/jpeg")
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "InvalidFileTypeError"
    assert "invoice" in body["detail"]
    assert "image/jpeg" in body["detail"]


async def test_upload_oversized_file_returns_413(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 1)
    oversized = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
    files = _three_valid_pdfs()
    files["bol"] = ("bol.pdf", oversized, "application/pdf")
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"] == "FileTooLargeError"
    assert "bol" in body["detail"]
    assert "1MB limit" in body["detail"]


async def test_upload_scanned_pdf_returns_422(client: AsyncClient) -> None:
    files = _three_valid_pdfs()
    files["packing_list"] = ("packing_list.pdf", _make_blank_pdf(), "application/pdf")
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "ImageOnlyPDFError"
    assert "packing_list" in body["detail"]
    assert "extractable text" in body["detail"]


async def test_upload_does_not_write_to_disk(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD: the upload flow must never write files to the working directory."""
    monkeypatch.chdir(tmp_path)
    before = set(os.listdir(tmp_path))

    files = _three_valid_pdfs()
    resp = await client.post("/upload", files=files)
    assert resp.status_code == 200

    after = set(os.listdir(tmp_path))
    assert after == before, f"Unexpected files created during upload: {after - before}"
