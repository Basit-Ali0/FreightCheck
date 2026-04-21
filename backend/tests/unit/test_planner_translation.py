"""Tests for planner Gemini invocation → execute_tool args mapping."""

from __future__ import annotations

import json

from freightcheck.schemas.gemini_outputs import PlannerToolInvocation, planner_invocation_to_args


def test_validate_field_match_mapping() -> None:
    inv = PlannerToolInvocation(
        name="validate_field_match",
        field="incoterm",
        doc_a="bol",
        doc_b="invoice",
        tolerance=0.0,
    )
    args = planner_invocation_to_args("validate_field_match", inv)
    assert args == {"field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0}


def test_validate_field_match_includes_peer_field() -> None:
    inv = PlannerToolInvocation(
        name="validate_field_match",
        field="gross_weight",
        doc_a="bol",
        doc_b="packing_list",
        tolerance=0.5,
        peer_field="total_weight",
    )
    args = planner_invocation_to_args("validate_field_match", inv)
    assert args["peer_field"] == "total_weight"


def test_re_extract_mapping() -> None:
    inv = PlannerToolInvocation(
        name="re_extract_field",
        doc_type="bol",
        field="shipper",
        hint="near header",
    )
    assert planner_invocation_to_args("re_extract_field", inv) == {
        "doc_type": "bol",
        "field": "shipper",
        "hint": "near header",
    }


def test_flag_exception_mapping_json_values() -> None:
    inv = PlannerToolInvocation(
        name="flag_exception",
        severity="warning",
        field="weight",
        description="mismatch",
        evidence_doc_a="bol",
        evidence_doc_b="invoice",
        evidence_val_a_json=json.dumps("12400"),
        evidence_val_b_json=json.dumps("13000"),
    )
    args = planner_invocation_to_args("flag_exception", inv)
    assert args["severity"] == "warning"
    assert args["evidence"]["doc_a"] == "bol"
    assert args["evidence"]["val_a"] == "12400"


def test_empty_tool_args() -> None:
    inv = PlannerToolInvocation(name="check_container_number_format")
    assert planner_invocation_to_args("check_container_number_format", inv) == {}


def test_unknown_tool_returns_empty_dict() -> None:
    inv = PlannerToolInvocation(name="custom")
    assert planner_invocation_to_args("custom", inv) == {}
