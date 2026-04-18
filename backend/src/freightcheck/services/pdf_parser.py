# backend/src/freightcheck/services/pdf_parser.py
"""In-memory PDF text extraction using PyMuPDF per System Design section 3.3.

This module never writes to disk. The caller passes the PDF bytes directly
(typically from a FastAPI `UploadFile`) and receives the concatenated raw
text of every page. Image-only PDFs are rejected with `ImageOnlyPDFError`
rather than returning an empty string.
"""

from __future__ import annotations

from typing import Any

import pymupdf

from freightcheck.errors import ImageOnlyPDFError, PDFParseError


def extract_raw_text(pdf_bytes: bytes) -> str:
    """Extract concatenated page text from an in-memory PDF.

    Parameters
    ----------
    pdf_bytes
        Raw PDF contents. Never a filesystem path — the parser is memory-only.

    Returns
    -------
    str
        Concatenated page text, one page per call to `get_text()`.

    Raises
    ------
    PDFParseError
        If PyMuPDF cannot open the stream (corrupted, empty, or not a PDF).
    ImageOnlyPDFError
        If the PDF opens but contains no extractable text across all pages.
    """
    if not pdf_bytes:
        raise PDFParseError("PDFParseError: received empty byte stream")

    try:
        doc: Any = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
    except pymupdf.FileDataError as exc:
        raise PDFParseError(f"PDFParseError: {exc}") from exc
    except (RuntimeError, ValueError, TypeError) as exc:
        raise PDFParseError(f"PDFParseError: {exc}") from exc

    try:
        pages_text = [page.get_text() for page in doc]
    finally:
        doc.close()

    combined = "".join(pages_text)
    if not combined.strip():
        raise ImageOnlyPDFError(
            "ImageOnlyPDFError: PDF contains no extractable text. "
            "Scanned PDFs are not supported in MVP.",
        )
    return combined
