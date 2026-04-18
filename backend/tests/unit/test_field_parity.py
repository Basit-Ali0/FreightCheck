# backend/tests/unit/test_field_parity.py
"""Guards against field-name drift between Pydantic, the Mongo schema example,
and the TypeScript interfaces.

The Data Models spec section 3 declares the Mongo document shape and section 4
declares the TypeScript interfaces; Implementation Rules forbids casing drift.
These tests lock the canonical field names in place so any spec-vs-code
divergence is caught at unit-test time rather than at runtime.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from freightcheck.schemas.agent import AuditSession, PlannerDecision, ToolCall
from freightcheck.schemas.audit import (
    AuditReport,
    Evidence,
    ExceptionRecord,
)
from freightcheck.schemas.documents import (
    BoLFields,
    ExtractionConfidence,
    InvoiceFields,
    LineItem,
    PackingListFields,
)

# tests/unit -> tests -> backend -> repo root; the frontend lives a sibling up.
TYPES_TS_PATH = Path(__file__).resolve().parents[3] / "frontend" / "src" / "types" / "index.ts"


AUDIT_SESSION_TOP_LEVEL_EXPECTED = {
    "session_id",
    "status",
    "created_at",
    "completed_at",
    "error_message",
    "extracted_fields",
    "extraction_confidence",
    "exceptions",
    "report",
    "tool_calls",
    "planner_decisions",
    "iteration_count",
    "needs_human_review",
    "review_reasons",
    "tokens_used",
    "elapsed_ms",
}

BOL_FIELDS_EXPECTED = {
    "bill_of_lading_number",
    "shipper",
    "consignee",
    "vessel_name",
    "port_of_loading",
    "port_of_discharge",
    "container_numbers",
    "description_of_goods",
    "gross_weight",
    "incoterm",
}

INVOICE_FIELDS_EXPECTED = {
    "invoice_number",
    "seller",
    "buyer",
    "invoice_date",
    "line_items",
    "total_value",
    "currency",
    "incoterm",
}

PACKING_LIST_FIELDS_EXPECTED = {
    "total_packages",
    "total_weight",
    "container_numbers",
    "line_items",
}

LINE_ITEM_EXPECTED = {"description", "quantity", "unit_price", "net_weight"}

EVIDENCE_EXPECTED = {"doc_a", "val_a", "doc_b", "val_b"}

EXCEPTION_RECORD_EXPECTED = {"exception_id", "severity", "field", "description", "evidence"}

AUDIT_REPORT_EXPECTED = {
    "critical_count",
    "warning_count",
    "info_count",
    "passed_count",
    "summary",
}

EXTRACTION_CONFIDENCE_EXPECTED = {"field", "value", "confidence", "rationale"}

TOOL_CALL_EXPECTED = {
    "tool_call_id",
    "iteration",
    "tool_name",
    "args",
    "result",
    "started_at",
    "completed_at",
    "duration_ms",
    "status",
    "error",
}

PLANNER_DECISION_EXPECTED = {
    "iteration",
    "chosen_tools",
    "rationale",
    "terminate",
    "created_at",
}


def _pydantic_fields(model_cls: type[BaseModel]) -> set[str]:
    return set(model_cls.model_fields.keys())


def test_audit_session_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(AuditSession) == AUDIT_SESSION_TOP_LEVEL_EXPECTED


def test_bol_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(BoLFields) == BOL_FIELDS_EXPECTED


def test_invoice_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(InvoiceFields) == INVOICE_FIELDS_EXPECTED


def test_packing_list_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(PackingListFields) == PACKING_LIST_FIELDS_EXPECTED


def test_line_item_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(LineItem) == LINE_ITEM_EXPECTED


def test_evidence_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(Evidence) == EVIDENCE_EXPECTED


def test_exception_record_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(ExceptionRecord) == EXCEPTION_RECORD_EXPECTED


def test_audit_report_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(AuditReport) == AUDIT_REPORT_EXPECTED


def test_extraction_confidence_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(ExtractionConfidence) == EXTRACTION_CONFIDENCE_EXPECTED


def test_tool_call_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(ToolCall) == TOOL_CALL_EXPECTED


def test_planner_decision_fields_match_mongo_schema() -> None:
    assert _pydantic_fields(PlannerDecision) == PLANNER_DECISION_EXPECTED


def test_types_ts_contains_every_canonical_field() -> None:
    """Every Pydantic field name must appear verbatim in the TypeScript types file.

    This guards against casing drift between the backend Pydantic models and
    the frontend contract. A failure here usually means a spec update did not
    propagate to one side.
    """
    content = TYPES_TS_PATH.read_text(encoding="utf-8")
    all_fields = (
        AUDIT_SESSION_TOP_LEVEL_EXPECTED
        | BOL_FIELDS_EXPECTED
        | INVOICE_FIELDS_EXPECTED
        | PACKING_LIST_FIELDS_EXPECTED
        | LINE_ITEM_EXPECTED
        | EVIDENCE_EXPECTED
        | EXCEPTION_RECORD_EXPECTED
        | AUDIT_REPORT_EXPECTED
        | EXTRACTION_CONFIDENCE_EXPECTED
        | TOOL_CALL_EXPECTED
        | PLANNER_DECISION_EXPECTED
    )
    missing = {field for field in all_fields if field not in content}
    assert not missing, f"TypeScript types/index.ts is missing fields: {missing}"
