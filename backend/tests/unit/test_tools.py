# backend/tests/unit/test_tools.py
"""Unit tests for every tool in `agent.tools` per Testing Spec §2.5.

Each tool has at least a happy path + an edge case. Gemini-backed tools are
tested by monkeypatching `services.gemini.call_gemini` so no network traffic
occurs.
"""

from __future__ import annotations

from typing import Any

import pytest

from freightcheck.agent import tools
from freightcheck.agent.tools import (
    ReExtractionResult,
    ToolContext,
    _SemanticResponse,
    check_container_consistency,
    check_container_number_format,
    check_incoterm_port_plausibility,
    escalate_to_human_review,
    flag_exception,
    iso_6346_is_valid,
    re_extract_field,
    validate_field_match,
    validate_field_semantic,
)
from freightcheck.errors import ExtractionError, ToolArgsValidationError
from freightcheck.schemas.audit import ExceptionSeverity, ValidationStatus
from tests.fixtures.container_numbers import (
    INVALID_CHECK_DIGIT,
    INVALID_FORMAT,
    VALID_CONTAINER_NUMBERS,
)


def _make_ctx(
    *,
    extracted: dict[str, Any] | None = None,
    confidence: dict[str, dict[str, dict[str, Any]]] | None = None,
    raw: dict[str, str] | None = None,
) -> ToolContext:
    return ToolContext(
        session_id="sess-test",
        extracted_fields=extracted or {},
        extraction_confidence=confidence or {},
        raw_texts=raw or {},
    )


# ---- validate_field_match ------------------------------------------------


def test_validate_field_match_numeric_within_tolerance_is_match() -> None:
    ctx = _make_ctx(
        extracted={"bol": {"gross_weight": 12400.0}, "packing_list": {"gross_weight": 12400.3}},
    )
    result = validate_field_match(ctx, "gross_weight", "bol", "packing_list", tolerance=0.5)
    assert result["status"] == ValidationStatus.MATCH.value
    assert ctx.validations == [result]


def test_validate_field_match_numeric_outside_tolerance_is_critical() -> None:
    ctx = _make_ctx(
        extracted={"bol": {"gross_weight": 12400.0}, "packing_list": {"gross_weight": 13200.0}},
    )
    result = validate_field_match(ctx, "gross_weight", "bol", "packing_list", tolerance=0.5)
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value


def test_validate_field_match_string_exact_match() -> None:
    ctx = _make_ctx(extracted={"bol": {"incoterm": "CIF"}, "invoice": {"incoterm": "cif  "}})
    result = validate_field_match(ctx, "incoterm", "bol", "invoice")
    assert result["status"] == ValidationStatus.MATCH.value


def test_validate_field_match_string_different() -> None:
    ctx = _make_ctx(extracted={"bol": {"incoterm": "CIF"}, "invoice": {"incoterm": "FOB"}})
    result = validate_field_match(ctx, "incoterm", "bol", "invoice")
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value


def test_validate_field_match_list_set_equality() -> None:
    ctx = _make_ctx(
        extracted={
            "bol": {"container_numbers": ["A", "B"]},
            "packing_list": {"container_numbers": ["B", "A"]},
        },
    )
    result = validate_field_match(ctx, "container_numbers", "bol", "packing_list")
    assert result["status"] == ValidationStatus.MATCH.value


def test_validate_field_match_missing_field_is_critical() -> None:
    ctx = _make_ctx(extracted={"bol": {}, "invoice": {"incoterm": "CIF"}})
    result = validate_field_match(ctx, "incoterm", "bol", "invoice")
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value
    assert "missing from bol" in result["reason"]


def test_validate_field_match_type_mismatch_raises() -> None:
    ctx = _make_ctx(extracted={"bol": {"incoterm": "CIF"}, "invoice": {"incoterm": ["CIF"]}})
    with pytest.raises(ValueError, match="Cannot compare"):
        validate_field_match(ctx, "incoterm", "bol", "invoice")


def test_validate_field_match_rejects_unknown_doc() -> None:
    ctx = _make_ctx()
    with pytest.raises(ToolArgsValidationError):
        validate_field_match(ctx, "incoterm", "bol", "unknown_doc")  # type: ignore[arg-type]


# ---- validate_field_semantic --------------------------------------------


async def test_validate_field_semantic_calls_gemini_and_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_gemini(**_kw: Any) -> tuple[_SemanticResponse, int]:
        return _SemanticResponse(status=ValidationStatus.MATCH, reason="Same entity"), 300

    monkeypatch.setattr(tools.gemini, "call_gemini", fake_call_gemini)

    ctx = _make_ctx(
        extracted={"bol": {"shipper": "Acme Exports Ltd"}, "invoice": {"shipper": "ACME"}},
    )
    result = await validate_field_semantic(ctx, "shipper", "bol", "invoice")
    assert result["status"] == ValidationStatus.MATCH.value
    assert result["reason"] == "Same entity"
    assert ctx.tokens_used == 300
    assert ctx.validations == [result]


async def test_validate_field_semantic_missing_field_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Should not call Gemini when either side is missing."""
    called = False

    async def fake_call_gemini(**_kw: Any) -> tuple[_SemanticResponse, int]:
        nonlocal called
        called = True
        return _SemanticResponse(status=ValidationStatus.MATCH, reason=""), 0

    monkeypatch.setattr(tools.gemini, "call_gemini", fake_call_gemini)

    ctx = _make_ctx(extracted={"bol": {}, "invoice": {"shipper": "ACME"}})
    result = await validate_field_semantic(ctx, "shipper", "bol", "invoice")
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value
    assert called is False


# ---- re_extract_field ---------------------------------------------------


async def test_re_extract_field_updates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call_gemini(**_kw: Any) -> tuple[ReExtractionResult, int]:
        return ReExtractionResult(value="CIF", confidence=0.95, rationale=None), 450

    monkeypatch.setattr(tools.gemini, "call_gemini", fake_call_gemini)

    ctx = _make_ctx(
        extracted={"bol": {"incoterm": None}},
        confidence={
            "bol": {
                "incoterm": {
                    "field": "incoterm",
                    "value": None,
                    "confidence": 0.4,
                    "rationale": "Unclear",
                },
            },
        },
        raw={"bol": "... gross weight 12400 kg ... incoterm CIF ..."},
    )
    result = await re_extract_field(ctx, "bol", "incoterm", hint="look near 'Incoterm'")

    assert result["value"] == "CIF"
    assert result["confidence"] == 0.95
    assert ctx.extracted_fields["bol"]["incoterm"] == "CIF"
    assert ctx.extraction_confidence["bol"]["incoterm"]["confidence"] == 0.95
    assert ctx.tokens_used == 450


async def test_re_extract_field_propagates_extraction_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_gemini(**_kw: Any) -> tuple[ReExtractionResult, int]:
        raise ExtractionError("ExtractionError: schema failed")

    monkeypatch.setattr(tools.gemini, "call_gemini", fake_call_gemini)

    ctx = _make_ctx(
        extracted={"bol": {"incoterm": "CIF"}},
        confidence={"bol": {"incoterm": {"field": "incoterm", "value": "CIF", "confidence": 0.5}}},
        raw={"bol": "text"},
    )
    with pytest.raises(ExtractionError):
        await re_extract_field(ctx, "bol", "incoterm", hint="hint")

    # Previous value must be preserved on failure.
    assert ctx.extracted_fields["bol"]["incoterm"] == "CIF"


# ---- check_container_consistency ----------------------------------------


def test_container_sets_match() -> None:
    ctx = _make_ctx(
        extracted={
            "bol": {"container_numbers": ["MSCU1234566", "CSQU3054383"]},
            "packing_list": {"container_numbers": ["CSQU3054383", "MSCU1234566"]},
        },
    )
    result = check_container_consistency(ctx)
    assert result["status"] == ValidationStatus.MATCH.value


def test_container_sets_differ_by_one() -> None:
    ctx = _make_ctx(
        extracted={
            "bol": {"container_numbers": ["MSCU1234566", "CSQU3054383"]},
            "packing_list": {"container_numbers": ["MSCU1234566"]},
        },
    )
    result = check_container_consistency(ctx)
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value
    assert "CSQU3054383" in result["reason"]


def test_container_consistency_missing_side_is_critical() -> None:
    ctx = _make_ctx(extracted={"bol": {"container_numbers": ["A"]}, "packing_list": {}})
    result = check_container_consistency(ctx)
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value


# ---- check_incoterm_port_plausibility -----------------------------------


def test_cif_without_destination_port_flags_critical() -> None:
    ctx = _make_ctx(
        extracted={
            "invoice": {"incoterm": "CIF"},
            "bol": {"port_of_loading": "Nhava Sheva, India", "port_of_discharge": ""},
        },
    )
    result = check_incoterm_port_plausibility(ctx)
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value
    assert "destination port" in result["reason"]


def test_fob_with_matching_origin_passes() -> None:
    ctx = _make_ctx(
        extracted={
            "invoice": {"incoterm": "FOB"},
            "bol": {"port_of_loading": "Shanghai, China", "port_of_discharge": ""},
        },
    )
    result = check_incoterm_port_plausibility(ctx)
    assert result["status"] == ValidationStatus.MATCH.value


def test_exw_returns_match_with_note() -> None:
    ctx = _make_ctx(
        extracted={
            "invoice": {"incoterm": "EXW"},
            "bol": {"port_of_loading": "Shanghai", "port_of_discharge": "Jebel Ali"},
        },
    )
    result = check_incoterm_port_plausibility(ctx)
    assert result["status"] == ValidationStatus.MATCH.value


def test_incoterm_port_plausibility_missing_incoterm() -> None:
    ctx = _make_ctx(
        extracted={
            "invoice": {},
            "bol": {"port_of_loading": "X", "port_of_discharge": "Y"},
        },
    )
    result = check_incoterm_port_plausibility(ctx)
    assert result["status"] == ValidationStatus.CRITICAL_MISMATCH.value


# ---- check_container_number_format / ISO 6346 ---------------------------


@pytest.mark.parametrize("cn", VALID_CONTAINER_NUMBERS)
def test_iso_6346_valid_numbers(cn: str) -> None:
    assert iso_6346_is_valid(cn) is True, f"{cn} should be valid"


@pytest.mark.parametrize("cn", INVALID_CHECK_DIGIT)
def test_iso_6346_invalid_check_digit(cn: str) -> None:
    assert iso_6346_is_valid(cn) is False, f"{cn} should fail check-digit"


@pytest.mark.parametrize("cn", INVALID_FORMAT)
def test_iso_6346_invalid_format(cn: str) -> None:
    assert iso_6346_is_valid(cn) is False, f"{cn} should fail format validation"


def test_check_container_number_format_all_valid() -> None:
    ctx = _make_ctx(
        extracted={
            "bol": {"container_numbers": ["MSCU1234566"]},
            "packing_list": {"container_numbers": ["CSQU3054383"]},
        },
    )
    result = check_container_number_format(ctx)
    assert result["ok"] is True
    assert result["checked"] == 2
    assert result["skipped"] is False
    assert result["created_exceptions"] == []
    assert ctx.exceptions == []


def test_check_container_number_format_flags_invalid_emits_warning_exception() -> None:
    # MSCU1234567 fails the ISO 6346 check-digit; MSCU1234566 is the valid
    # variant. The tool must surface a `warning` ExceptionRecord — not a
    # ValidationResult with `minor_mismatch` — per Data Models §5 because
    # this is a single-document sanity check, not a cross-document
    # comparison (decided 2026-04-18 when Q-004 was resolved).
    ctx = _make_ctx(
        extracted={
            "bol": {"container_numbers": ["MSCU1234566", "MSCU1234567"]},
            "packing_list": {"container_numbers": ["MSCU1234566"]},
        },
    )
    result = check_container_number_format(ctx)

    assert result["ok"] is False
    assert result["checked"] == 3
    assert len(result["created_exceptions"]) == 1
    assert ctx.exceptions == result["created_exceptions"]

    record = ctx.exceptions[0]
    assert record["severity"] == ExceptionSeverity.WARNING.value
    assert record["field"] == "container_number_format"
    assert "MSCU1234567" in record["description"]
    assert record["evidence"]["doc_a"] == "bol"
    assert record["evidence"]["val_a"] == "MSCU1234567"
    assert record["evidence"]["doc_b"] == "iso_6346_spec"
    assert "check digit" in record["evidence"]["val_b"] or "mod-11" in record["evidence"]["val_b"]
    assert record["exception_id"]


def test_check_container_number_format_flags_each_invalid_separately() -> None:
    ctx = _make_ctx(
        extracted={
            "bol": {"container_numbers": ["MSCU1234567"]},
            "packing_list": {"container_numbers": ["MSCU1234568"]},
        },
    )
    result = check_container_number_format(ctx)
    assert result["ok"] is False
    assert len(result["created_exceptions"]) == 2
    sources = {e["evidence"]["doc_a"] for e in ctx.exceptions}
    assert sources == {"bol", "packing_list"}
    severities = {e["severity"] for e in ctx.exceptions}
    assert severities == {ExceptionSeverity.WARNING.value}


def test_check_container_number_format_no_containers_is_skip_no_exception() -> None:
    # Precondition failure: the tool can't run, but this is not itself a
    # finding. The planner decides whether to `escalate_to_human_review`.
    ctx = _make_ctx(extracted={"bol": {}, "packing_list": {}})
    result = check_container_number_format(ctx)
    assert result["ok"] is True
    assert result["checked"] == 0
    assert result["skipped"] is True
    assert result["created_exceptions"] == []
    assert ctx.exceptions == []


# ---- flag_exception -----------------------------------------------------


def test_flag_exception_appends_to_state() -> None:
    ctx = _make_ctx()
    result = flag_exception(
        ctx,
        severity="critical",
        field="incoterm",
        description="Incoterm differs between BoL and Invoice",
        evidence={"doc_a": "bol", "val_a": "CIF", "doc_b": "invoice", "val_b": "FOB"},
    )
    assert result["severity"] == "critical"
    assert len(ctx.exceptions) == 1
    assert ctx.exceptions[0]["field"] == "incoterm"
    assert "exception_id" in ctx.exceptions[0]


def test_flag_exception_invalid_severity_raises() -> None:
    ctx = _make_ctx()
    with pytest.raises(ToolArgsValidationError):
        flag_exception(
            ctx,
            severity="catastrophic",  # type: ignore[arg-type]
            field="x",
            description="y",
            evidence={"doc_a": "bol", "val_a": 1, "doc_b": "invoice", "val_b": 2},
        )


def test_flag_exception_malformed_evidence_raises() -> None:
    ctx = _make_ctx()
    with pytest.raises(ToolArgsValidationError):
        flag_exception(
            ctx,
            severity="warning",
            field="x",
            description="y",
            evidence={"missing_required_keys": True},
        )


# ---- escalate_to_human_review -------------------------------------------


def test_escalate_sets_needs_human_review() -> None:
    ctx = _make_ctx()
    result = escalate_to_human_review(
        ctx,
        reason="gross_weight extracted with confidence 0.42",
    )
    assert ctx.needs_human_review is True
    assert ctx.review_reasons == ["gross_weight extracted with confidence 0.42"]
    assert result["needs_human_review"] is True
    assert result["total_reasons"] == 1


def test_escalate_rejects_empty_reason() -> None:
    ctx = _make_ctx()
    with pytest.raises(ToolArgsValidationError):
        escalate_to_human_review(ctx, reason="   ")


# ---- TOOL_REGISTRY ------------------------------------------------------


def test_tool_registry_exposes_all_eight_tools() -> None:
    expected = {
        "validate_field_match",
        "validate_field_semantic",
        "re_extract_field",
        "check_container_consistency",
        "check_incoterm_port_plausibility",
        "check_container_number_format",
        "flag_exception",
        "escalate_to_human_review",
    }
    assert set(tools.TOOL_REGISTRY.keys()) == expected


def test_every_registered_tool_has_a_docstring() -> None:
    for name, fn in tools.TOOL_REGISTRY.items():
        doc = fn.__doc__
        assert doc is not None, f"Tool {name} is missing a docstring"
        assert doc.strip(), f"Tool {name} has an empty docstring"
