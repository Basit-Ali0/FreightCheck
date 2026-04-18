# backend/src/freightcheck/errors.py
"""Custom exception hierarchy for FreightCheck per Error Handling spec section 1.

Every raised exception in application code must be a subclass of
`FreightCheckError`. FastAPI exception handlers use these classes to map to
the HTTP error shapes defined in the API Contract.
"""

from typing import Any


class FreightCheckError(Exception):
    """Base class for all FreightCheck errors.

    Carries a structured `context` dict for logging alongside the message.
    """

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.context: dict[str, Any] = context


# ---- Upload / PDF layer --------------------------------------------------


class InvalidFileTypeError(FreightCheckError):
    """Uploaded file is not a PDF (wrong MIME type or extension)."""


class FileTooLargeError(FreightCheckError):
    """Uploaded file exceeds `MAX_FILE_SIZE_MB`."""


class ImageOnlyPDFError(FreightCheckError):
    """PDF contains no extractable text — scanned/image-only PDFs are rejected."""


class PDFParseError(FreightCheckError):
    """PyMuPDF failed to open or read the PDF (corrupted or malformed)."""


class MissingDocumentError(FreightCheckError):
    """One or more of the required documents (bol, invoice, packing_list) is absent."""


# ---- Session layer -------------------------------------------------------


class SessionNotFoundError(FreightCheckError):
    """Lookup by `session_id` found nothing in either the upload cache or Mongo."""


class DuplicateAuditError(FreightCheckError):
    """An audit has already been triggered for this session_id."""


# ---- Gemini layer --------------------------------------------------------


class GeminiAPIError(FreightCheckError):
    """Network, auth, or rate-limit failure from Gemini."""


class ExtractionError(FreightCheckError):
    """Gemini produced unusable output for an extraction prompt after retries."""


class PlannerError(FreightCheckError):
    """Planner call failed or returned malformed output after retries."""


class SemanticValidationError(FreightCheckError):
    """Semantic validator prompt failed after retries."""


# ---- Agent layer ---------------------------------------------------------


class InvalidToolError(FreightCheckError):
    """Planner requested a tool that is not in TOOL_REGISTRY."""


class ToolArgsValidationError(FreightCheckError):
    """Planner provided arguments that fail the tool's Pydantic args schema."""


class AgentBudgetError(FreightCheckError):
    """Iteration, token, or time budget exhausted. Graceful termination, not a crash."""


# ---- Database layer ------------------------------------------------------


class DatabaseError(FreightCheckError):
    """MongoDB read/write failure."""
