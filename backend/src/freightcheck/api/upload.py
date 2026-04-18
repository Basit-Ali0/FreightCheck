# backend/src/freightcheck/api/upload.py
"""POST /upload endpoint per API Contract.

Accepts exactly three PDFs (bol, invoice, packing_list), extracts their raw
text in-memory, caches the result under a new uuid4 `session_id`, and
returns an `UploadResponse`. Every failure is raised as a subclass of
`FreightCheckError` so that the app-wide exception handlers in `main.py`
produce the error shape defined in the API Contract.
"""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import APIRouter, File, UploadFile

from freightcheck.errors import (
    FileTooLargeError,
    ImageOnlyPDFError,
    InvalidFileTypeError,
    MissingDocumentError,
    PDFParseError,
)
from freightcheck.schemas.api import UploadResponse
from freightcheck.services import pdf_parser, upload_cache
from freightcheck.settings import settings

router = APIRouter(tags=["upload"])
log = structlog.get_logger()

_DOC_KEYS = ("bol", "invoice", "packing_list")


def _bytes_to_mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f}MB"


def _validate_pdf_filetype(doc_key: str, file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    looks_like_pdf = content_type == "application/pdf" or filename.endswith(".pdf")
    if not looks_like_pdf:
        received = file.content_type or "unknown"
        raise InvalidFileTypeError(
            f"File '{doc_key}' must be a PDF. Received: {received}",
            doc_key=doc_key,
            content_type=file.content_type,
        )


@router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_documents(
    bol: UploadFile | None = File(default=None),
    invoice: UploadFile | None = File(default=None),
    packing_list: UploadFile | None = File(default=None),
) -> UploadResponse:
    """Upload three shipping PDFs and cache their raw text for a subsequent /audit call."""
    started = time.perf_counter()
    files_by_key: dict[str, UploadFile] = {}
    for key, file in (("bol", bol), ("invoice", invoice), ("packing_list", packing_list)):
        if file is not None and (file.filename or file.content_type):
            files_by_key[key] = file

    missing = [k for k in _DOC_KEYS if k not in files_by_key]
    if missing:
        raise MissingDocumentError(
            "All three documents are required: bol, invoice, packing_list. "
            f"Missing: {', '.join(missing)}",
            missing=missing,
        )

    session_id = str(uuid.uuid4())
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    raw_bytes_by_key: dict[str, bytes] = {}
    for key in _DOC_KEYS:
        file = files_by_key[key]
        _validate_pdf_filetype(key, file)
        data = await file.read()
        if len(data) > max_bytes:
            raise FileTooLargeError(
                f"File '{key}' exceeds the {settings.MAX_FILE_SIZE_MB}MB limit. "
                f"Received: {_bytes_to_mb(len(data))}",
                doc_key=key,
                size_bytes=len(data),
            )
        raw_bytes_by_key[key] = data

    total_bytes = sum(len(b) for b in raw_bytes_by_key.values())
    log.info(
        "upload.received",
        session_id=session_id,
        bytes_received=total_bytes,
        files_count=len(raw_bytes_by_key),
    )

    raw_texts: dict[str, str] = {}
    for key in _DOC_KEYS:
        try:
            raw_texts[key] = pdf_parser.extract_raw_text(raw_bytes_by_key[key])
        except ImageOnlyPDFError as exc:
            raise ImageOnlyPDFError(
                f"File '{key}' contains no extractable text. "
                "Scanned PDFs are not supported in MVP.",
                doc_key=key,
            ) from exc
        except PDFParseError as exc:
            raise PDFParseError(
                f"Failed to extract text from '{key}'. The file may be corrupted.",
                doc_key=key,
            ) from exc

    upload_cache.put(session_id, raw_texts)

    raw_text_lengths = {k: len(v) for k, v in raw_texts.items()}
    duration_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "upload.parsed",
        session_id=session_id,
        raw_text_lengths=raw_text_lengths,
        duration_ms=duration_ms,
    )

    return UploadResponse(
        session_id=session_id,
        message="Documents uploaded and parsed successfully",
        documents_received=list(_DOC_KEYS),
        raw_text_lengths=raw_text_lengths,
    )
