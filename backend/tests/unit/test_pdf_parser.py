# backend/tests/unit/test_pdf_parser.py
"""Unit tests for `services.pdf_parser` covering happy path and every failure mode."""

from __future__ import annotations

import pymupdf
import pytest

from freightcheck.errors import ImageOnlyPDFError, PDFParseError
from freightcheck.services.pdf_parser import extract_raw_text


def _make_text_pdf(text: str) -> bytes:
    """Build an in-memory PDF whose single page contains `text`."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = doc.tobytes()
    doc.close()
    return bytes(buf)


def _make_blank_pdf(page_count: int = 1) -> bytes:
    """Build an in-memory PDF with blank pages (simulates a scanned/image-only PDF)."""
    doc = pymupdf.open()
    for _ in range(page_count):
        doc.new_page()
    buf = doc.tobytes()
    doc.close()
    return bytes(buf)


def test_extract_raw_text_happy_path() -> None:
    text = "Bill of Lading number MSKU1234567"
    pdf_bytes = _make_text_pdf(text)
    result = extract_raw_text(pdf_bytes)
    assert text in result


def test_extract_raw_text_preserves_multi_page_content() -> None:
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} content")
    pdf_bytes = bytes(doc.tobytes())
    doc.close()

    result = extract_raw_text(pdf_bytes)
    for i in range(3):
        assert f"Page {i + 1} content" in result


def test_extract_raw_text_rejects_empty_bytes() -> None:
    with pytest.raises(PDFParseError):
        extract_raw_text(b"")


def test_extract_raw_text_rejects_non_pdf_bytes() -> None:
    with pytest.raises(PDFParseError):
        extract_raw_text(b"Not a PDF at all, just plain text bytes.")


def test_extract_raw_text_rejects_scanned_pdf() -> None:
    pdf_bytes = _make_blank_pdf()
    with pytest.raises(ImageOnlyPDFError):
        extract_raw_text(pdf_bytes)


def test_extract_raw_text_rejects_corrupted_pdf_header() -> None:
    pdf_bytes = b"%PDF-1.4\nthis is not actually a valid PDF body\n%%EOF"
    with pytest.raises(PDFParseError):
        extract_raw_text(pdf_bytes)
