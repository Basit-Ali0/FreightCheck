# backend/src/freightcheck/schemas/audit.py
"""Validation, exception, report, and session-status models per Data Models spec section 1.3."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ValidationStatus(str, Enum):
    """Outcome of a single validation comparison."""

    MATCH = "match"
    MINOR_MISMATCH = "minor_mismatch"
    CRITICAL_MISMATCH = "critical_mismatch"


class ExceptionSeverity(str, Enum):
    """Severity assigned to an exception surfaced on the audit report."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SessionStatus(str, Enum):
    """Lifecycle status of an audit session."""

    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    AWAITING_REVIEW = "awaiting_review"


class ValidationResult(BaseModel):
    """Output of a single validation tool call."""

    field: str
    doc_a: str
    val_a: Any
    doc_b: str
    val_b: Any
    status: ValidationStatus
    reason: str


class Evidence(BaseModel):
    """Traceability trail embedded inside every `ExceptionRecord`."""

    doc_a: str
    val_a: Any
    doc_b: str
    val_b: Any


class ExceptionRecord(BaseModel):
    """A single flagged discrepancy produced by `flag_exception`."""

    exception_id: str
    severity: ExceptionSeverity
    field: str
    description: str
    evidence: Evidence


class AuditReport(BaseModel):
    """Compiled final output of the agent, written on completion."""

    critical_count: int
    warning_count: int
    info_count: int
    passed_count: int
    summary: str
