"""Curated expected-tool sets per scenario kind (Evaluation Spec §2.6)."""

from __future__ import annotations

# Approximate minimal sensible tool coverage — planner may add re_extract / semantic calls.
_EXPECTED_TOOLS: dict[str, frozenset[str]] = {
    "consistent": frozenset(
        {
            "validate_field_match",
            "check_container_consistency",
            "check_container_number_format",
        },
    ),
    "duplicate_line_items": frozenset(
        {"validate_field_match", "validate_field_semantic", "check_container_consistency"},
    ),
    "duplicate_line_items_mismatch": frozenset(
        {"validate_field_match", "validate_field_semantic", "flag_exception"},
    ),
    "incoterm_conflict": frozenset({"validate_field_match", "flag_exception"}),
    "quantity_mismatch": frozenset({"validate_field_match", "flag_exception"}),
    "weight_mismatch_outside_tolerance": frozenset({"validate_field_match", "flag_exception"}),
    "weight_mismatch_within_tolerance": frozenset({"validate_field_match"}),
    "currency_symbol_ambiguous": frozenset(
        {"validate_field_match", "validate_field_semantic", "check_container_consistency"},
    ),
    "container_number_mismatch": frozenset(
        {"check_container_consistency", "check_container_number_format", "flag_exception"},
    ),
    "invalid_container_check_digit": frozenset(
        {"check_container_number_format", "check_container_consistency", "flag_exception"},
    ),
    "incoterm_port_contradiction": frozenset(
        {"check_incoterm_port_plausibility", "validate_field_match", "flag_exception"},
    ),
    "low_quality_pdf": frozenset({"validate_field_match", "re_extract_field"}),
    "description_semantic_match": frozenset({"validate_field_semantic", "validate_field_match"}),
    "description_semantic_mismatch": frozenset({"validate_field_semantic", "flag_exception"}),
    "injection_override": frozenset({"validate_field_match", "check_container_consistency"}),
    "injection_fake_tag": frozenset({"validate_field_match"}),
    "missing_field": frozenset({"validate_field_match", "re_extract_field"}),
}


def expected_tool_names(scenario_kind: str) -> frozenset[str]:
    return _EXPECTED_TOOLS.get(
        scenario_kind,
        frozenset({"validate_field_match", "check_container_consistency"}),
    )
