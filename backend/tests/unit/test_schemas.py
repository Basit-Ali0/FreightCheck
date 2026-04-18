# backend/tests/unit/test_schemas.py
"""Roundtrip tests for every Pydantic model per Milestone 1 Definition of Done.

Each model is exercised with `.model_dump()` followed by `.model_validate()`,
and the reconstructed instance must equal the original. The models are
canonical across Pydantic, MongoDB, and the API contract, so any divergence
caught here is a real drift.
"""

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError

from freightcheck.schemas.agent import AuditSession, PlannerDecision, ToolCall
from freightcheck.schemas.api import (
    AuditRequest,
    AuditResponse,
    SessionListResponse,
    SessionSummary,
    TrajectoryResponse,
    UploadResponse,
)
from freightcheck.schemas.audit import (
    AuditReport,
    Evidence,
    ExceptionRecord,
    ExceptionSeverity,
    SessionStatus,
    ValidationResult,
    ValidationStatus,
)
from freightcheck.schemas.documents import (
    BoLFields,
    ExtractedDocument,
    ExtractionConfidence,
    InvoiceFields,
    LineItem,
    PackingListFields,
)


def _roundtrip(instance: BaseModel) -> BaseModel:
    """Dump then re-validate a model instance and return the reconstructed object."""
    cls = type(instance)
    return cls.model_validate(instance.model_dump())


def _line_item_invoice() -> LineItem:
    return LineItem(description="Cotton Fabric", quantity=500, unit_price=12.50)


def _line_item_packing() -> LineItem:
    return LineItem(description="Cotton Fabric", quantity=500, net_weight=248.0)


def _bol_fields() -> BoLFields:
    return BoLFields(
        bill_of_lading_number="MSKU1234567",
        shipper="Acme Exports Pvt Ltd",
        consignee="Global Traders LLC",
        vessel_name="MSC AURORA",
        port_of_loading="Nhava Sheva, India",
        port_of_discharge="Jebel Ali, UAE",
        container_numbers=["MSCU1234567", "MSCU7654321"],
        description_of_goods="Textile Goods — Cotton Fabric",
        gross_weight=12400.0,
        incoterm="CIF",
    )


def _invoice_fields() -> InvoiceFields:
    return InvoiceFields(
        invoice_number="INV-2026-0042",
        seller="Acme Exports Pvt Ltd",
        buyer="Global Traders LLC",
        invoice_date="2026-04-10",
        line_items=[_line_item_invoice()],
        total_value=6250.00,
        currency="USD",
        incoterm="FOB",
    )


def _packing_list_fields() -> PackingListFields:
    return PackingListFields(
        total_packages=50,
        total_weight=12400.0,
        container_numbers=["MSCU1234567", "MSCU7654321"],
        line_items=[_line_item_packing()],
    )


def _extraction_confidence_high() -> ExtractionConfidence:
    return ExtractionConfidence(field="incoterm", value="CIF", confidence=0.98)


def _extraction_confidence_low() -> ExtractionConfidence:
    return ExtractionConfidence(
        field="gross_weight",
        value=12400.0,
        confidence=0.42,
        rationale="Weight appears in two places with conflicting values.",
    )


def _evidence() -> Evidence:
    return Evidence(doc_a="bol", val_a="CIF", doc_b="invoice", val_b="FOB")


def _exception_record() -> ExceptionRecord:
    return ExceptionRecord(
        exception_id="e1a2b3c4-0001",
        severity=ExceptionSeverity.CRITICAL,
        field="incoterm",
        description=(
            "Incoterm is 'CIF' on the Bill of Lading but 'FOB' on the Commercial Invoice."
        ),
        evidence=_evidence(),
    )


def _audit_report() -> AuditReport:
    return AuditReport(
        critical_count=1,
        warning_count=1,
        info_count=0,
        passed_count=8,
        summary="1 critical incoterm conflict detected between BoL and Invoice.",
    )


def _validation_result() -> ValidationResult:
    return ValidationResult(
        field="incoterm",
        doc_a="bol",
        val_a="CIF",
        doc_b="invoice",
        val_b="FOB",
        status=ValidationStatus.CRITICAL_MISMATCH,
        reason="Exact string mismatch on trade term code",
    )


def _tool_call() -> ToolCall:
    started = datetime(2026, 4, 18, 10, 30, 15, 120_000, tzinfo=UTC)
    completed = datetime(2026, 4, 18, 10, 30, 15, 140_000, tzinfo=UTC)
    return ToolCall(
        tool_call_id="tc-0001",
        iteration=1,
        tool_name="validate_field_match",
        args={"field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0},
        result={"status": "critical_mismatch", "val_a": "CIF", "val_b": "FOB"},
        started_at=started,
        completed_at=completed,
        duration_ms=20,
        status="success",
        error=None,
    )


def _planner_decision() -> PlannerDecision:
    return PlannerDecision(
        iteration=1,
        chosen_tools=["validate_field_match", "check_container_consistency"],
        rationale="Both incoterm values extracted with high confidence.",
        terminate=False,
        created_at=datetime(2026, 4, 18, 10, 30, 15, 100_000, tzinfo=UTC),
    )


def _audit_session() -> AuditSession:
    return AuditSession(
        session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef",
        status=SessionStatus.COMPLETE,
        created_at=datetime(2026, 4, 18, 10, 30, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 18, 10, 30, 22, tzinfo=UTC),
        error_message=None,
        extracted_fields={
            "bol": _bol_fields().model_dump(),
            "invoice": _invoice_fields().model_dump(),
            "packing_list": _packing_list_fields().model_dump(),
        },
        extraction_confidence={
            "bol": {"incoterm": _extraction_confidence_high()},
        },
        exceptions=[_exception_record()],
        report=_audit_report(),
        tool_calls=[_tool_call()],
        planner_decisions=[_planner_decision()],
        iteration_count=3,
        needs_human_review=False,
        review_reasons=[],
        tokens_used=18_420,
        elapsed_ms=22_100,
    )


MODEL_FACTORIES = [
    pytest.param(_line_item_invoice, id="LineItem_invoice"),
    pytest.param(_line_item_packing, id="LineItem_packing"),
    pytest.param(_bol_fields, id="BoLFields"),
    pytest.param(_invoice_fields, id="InvoiceFields"),
    pytest.param(_packing_list_fields, id="PackingListFields"),
    pytest.param(_extraction_confidence_high, id="ExtractionConfidence_high"),
    pytest.param(_extraction_confidence_low, id="ExtractionConfidence_low"),
    pytest.param(
        lambda: ExtractedDocument(
            fields=_bol_fields(),
            confidences={"incoterm": _extraction_confidence_high()},
        ),
        id="ExtractedDocument_bol",
    ),
    pytest.param(
        lambda: ExtractedDocument(
            fields=_invoice_fields(),
            confidences={"invoice_number": _extraction_confidence_high()},
        ),
        id="ExtractedDocument_invoice",
    ),
    pytest.param(
        lambda: ExtractedDocument(
            fields=_packing_list_fields(),
            confidences={"total_weight": _extraction_confidence_high()},
        ),
        id="ExtractedDocument_packing_list",
    ),
    pytest.param(_validation_result, id="ValidationResult"),
    pytest.param(_evidence, id="Evidence"),
    pytest.param(_exception_record, id="ExceptionRecord"),
    pytest.param(_audit_report, id="AuditReport"),
    pytest.param(_tool_call, id="ToolCall"),
    pytest.param(_planner_decision, id="PlannerDecision"),
    pytest.param(_audit_session, id="AuditSession"),
    pytest.param(
        lambda: UploadResponse(
            session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef",
            message="Documents uploaded and parsed successfully",
            documents_received=["bol", "invoice", "packing_list"],
            raw_text_lengths={"bol": 1842, "invoice": 2310, "packing_list": 987},
        ),
        id="UploadResponse",
    ),
    pytest.param(
        lambda: AuditRequest(session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef"),
        id="AuditRequest",
    ),
    pytest.param(
        lambda: AuditResponse(
            session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef",
            status=SessionStatus.PROCESSING,
            message="Audit started.",
            created_at=datetime(2026, 4, 18, 10, 30, 0, tzinfo=UTC),
        ),
        id="AuditResponse",
    ),
    pytest.param(
        lambda: SessionSummary(
            session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef",
            status=SessionStatus.COMPLETE,
            created_at=datetime(2026, 4, 18, 10, 30, 0, tzinfo=UTC),
            completed_at=datetime(2026, 4, 18, 10, 30, 22, tzinfo=UTC),
            critical_count=2,
            warning_count=1,
            info_count=0,
            needs_human_review=False,
            iteration_count=3,
        ),
        id="SessionSummary_complete",
    ),
    pytest.param(
        lambda: SessionSummary(
            session_id="9b2e4f1a-12c3-4d5e-b678-901234cdef56",
            status=SessionStatus.FAILED,
            created_at=datetime(2026, 4, 18, 9, 15, 0, tzinfo=UTC),
        ),
        id="SessionSummary_failed_defaults",
    ),
    pytest.param(
        lambda: SessionListResponse(
            sessions=[
                SessionSummary(
                    session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef",
                    status=SessionStatus.PROCESSING,
                    created_at=datetime(2026, 4, 18, 10, 30, 0, tzinfo=UTC),
                ),
            ],
            total=1,
        ),
        id="SessionListResponse",
    ),
    pytest.param(
        lambda: TrajectoryResponse(
            session_id="3f7a1c2d-89b4-4e6f-a123-456789abcdef",
            status=SessionStatus.COMPLETE,
            iteration_count=3,
            planner_decisions=[_planner_decision()],
            tool_calls=[_tool_call()],
            tokens_used=18_420,
            elapsed_ms=22_100,
        ),
        id="TrajectoryResponse",
    ),
]


@pytest.mark.parametrize("factory", MODEL_FACTORIES)
def test_model_roundtrip(factory: object) -> None:
    """Every Pydantic model roundtrips through model_dump + model_validate."""
    original = factory()  # type: ignore[operator]
    assert isinstance(original, BaseModel)
    restored = _roundtrip(original)
    assert restored == original


def test_extraction_confidence_rejects_out_of_range() -> None:
    """Confidence must be constrained to [0.0, 1.0] per Data Models section 1.2."""
    with pytest.raises(ValidationError):
        ExtractionConfidence(field="x", value=1, confidence=1.1)
    with pytest.raises(ValidationError):
        ExtractionConfidence(field="x", value=1, confidence=-0.1)


def test_audit_session_defaults_are_fresh_instances() -> None:
    """Default list/dict factories must not share state across instances."""
    a = AuditSession(
        session_id="a",
        status=SessionStatus.PROCESSING,
        created_at=datetime(2026, 4, 18, tzinfo=UTC),
    )
    b = AuditSession(
        session_id="b",
        status=SessionStatus.PROCESSING,
        created_at=datetime(2026, 4, 18, tzinfo=UTC),
    )
    a.exceptions.append(_exception_record())
    a.tool_calls.append(_tool_call())
    assert b.exceptions == []
    assert b.tool_calls == []


def test_session_status_values_match_spec() -> None:
    """Enum values must exactly match the Data Models spec strings."""
    assert {s.value for s in SessionStatus} == {
        "processing",
        "complete",
        "failed",
        "awaiting_review",
    }


def test_exception_severity_values_match_spec() -> None:
    """Enum values must exactly match the Data Models spec strings."""
    assert {s.value for s in ExceptionSeverity} == {"info", "warning", "critical"}


def test_validation_status_values_match_spec() -> None:
    """Enum values must exactly match the Data Models spec strings."""
    assert {s.value for s in ValidationStatus} == {
        "match",
        "minor_mismatch",
        "critical_mismatch",
    }
