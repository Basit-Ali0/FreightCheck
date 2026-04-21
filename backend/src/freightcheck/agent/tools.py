# backend/src/freightcheck/agent/tools.py
"""Agent tools per System Design section 5.5.

The planner selects tools from `TOOL_REGISTRY`; the dispatcher invokes them
with a `ToolContext` carrying the slice of `AgentState` each tool needs to
read or mutate. Docstrings on each tool are copied verbatim from the spec so
the planner LLM sees the same contract we do.

Tool contract (M3 scope):
- Deterministic tools never raise; unresolvable inputs produce a
  `critical_mismatch` ValidationResult. See Error Handling spec section 4.
- Gemini-backed tools (`validate_field_semantic`, `re_extract_field`)
  propagate `SemanticValidationError` / `ExtractionError` / `GeminiAPIError`
  so the dispatcher records them as failed ToolCalls.
- State-mutation tools (`flag_exception`, `escalate_to_human_review`) append
  to the shared `ToolContext` lists; they never raise.

`TOOL_REGISTRY` holds LangChain `StructuredTool` instances so Gemini receives
native JSON Schemas via `build_planner_gemini_tools()`; the dispatcher is the
only execution path and calls `TOOL_IMPLEMENTATIONS` with a `ToolContext`.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from google.genai import types as genai_types
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict

from freightcheck.agent import prompts
from freightcheck.errors import ToolArgsValidationError
from freightcheck.schemas.audit import (
    Evidence,
    ExceptionRecord,
    ExceptionSeverity,
    ValidationResult,
    ValidationStatus,
)
from freightcheck.schemas.gemini_outputs import (
    parse_wire_json_value,
    re_extraction_parsed_to_entry,
    re_extraction_response_schema,
)
from freightcheck.services import gemini

DocType = Literal["bol", "invoice", "packing_list"]
_DOC_TYPES: tuple[DocType, ...] = ("bol", "invoice", "packing_list")


@dataclass
class ToolContext:
    """Mutable slice of `AgentState` passed to every tool invocation.

    The dispatcher constructs this from the current graph state before a
    tool call and merges it back after. Tools read `extracted_fields`,
    `extraction_confidence`, and `raw_texts`; they mutate `validations`,
    `exceptions`, `needs_human_review`, `review_reasons`, and
    `tokens_used`.
    """

    session_id: str
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    extraction_confidence: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    raw_texts: dict[str, str] = field(default_factory=dict)
    validations: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[dict[str, Any]] = field(default_factory=list)
    needs_human_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    tokens_used: int = 0


_MISSING = object()


def _get_field(extracted: dict[str, Any], doc: str, field_name: str) -> Any:
    """Fetch `extracted[doc][field_name]` or return the sentinel `_MISSING`."""
    doc_fields = extracted.get(doc)
    if not isinstance(doc_fields, dict):
        return _MISSING
    if field_name not in doc_fields:
        return _MISSING
    return doc_fields[field_name]


def _nullable(value: Any) -> Any:
    """Normalise the `_MISSING` sentinel to `None` for JSON serialisation."""
    return None if value is _MISSING else value


def _validate_doc_keys(*docs: str) -> None:
    for doc in docs:
        if doc not in _DOC_TYPES:
            raise ToolArgsValidationError(
                f"ToolArgsValidationError: doc must be one of {_DOC_TYPES}, got {doc!r}",
                doc=doc,
            )


def _sum_line_item_quantities(extracted: dict[str, Any], doc: str) -> Any:
    items = _get_field(extracted, doc, "line_items")
    if items is _MISSING or not isinstance(items, list):
        return _MISSING
    total = 0.0
    for row in items:
        if not isinstance(row, dict):
            continue
        q = row.get("quantity")
        if q is None:
            return _MISSING
        try:
            total += float(q)
        except (TypeError, ValueError, ArithmeticError):
            return _MISSING
    return total


def _first_invoice_line_description(ctx: ToolContext) -> Any:
    inv = ctx.extracted_fields.get("invoice")
    if not isinstance(inv, dict):
        return _MISSING
    items = inv.get("line_items")
    if not isinstance(items, list) or not items:
        return _MISSING
    row0 = items[0]
    if not isinstance(row0, dict):
        return _MISSING
    if "description" not in row0:
        return _MISSING
    return row0.get("description")


def _validate_total_quantity_match(
    ctx: ToolContext,
    doc_a: DocType,
    doc_b: DocType,
) -> dict[str, Any]:
    """Data Models §5 `total_quantity`: sum of line item quantities, exact match."""
    q_a = _sum_line_item_quantities(ctx.extracted_fields, doc_a)
    q_b = _sum_line_item_quantities(ctx.extracted_fields, doc_b)
    field_name = "total_quantity"
    if q_a is _MISSING:
        return _build_result(
            ctx,
            field_name,
            doc_a,
            None,
            doc_b,
            q_b if q_b is not _MISSING else None,
            ValidationStatus.CRITICAL_MISMATCH,
            f"Could not derive total quantity from {doc_a} line_items.",
        )
    if q_b is _MISSING:
        return _build_result(
            ctx,
            field_name,
            doc_a,
            q_a,
            doc_b,
            None,
            ValidationStatus.CRITICAL_MISMATCH,
            f"Could not derive total quantity from {doc_b} line_items.",
        )
    diff = abs(float(q_a) - float(q_b))
    if diff <= 0.0:
        return _build_result(
            ctx,
            field_name,
            doc_a,
            q_a,
            doc_b,
            q_b,
            ValidationStatus.MATCH,
            "Total quantities (sum of line_items.quantity) match exactly.",
        )
    return _build_result(
        ctx,
        field_name,
        doc_a,
        q_a,
        doc_b,
        q_b,
        ValidationStatus.CRITICAL_MISMATCH,
        f"Total quantity mismatch: {q_a} vs {q_b} (exact match required).",
    )


def _invoice_total_line_items_error(
    ctx: ToolContext,
    total_value: Any,
    compared_value: Any,
    reason: str,
) -> dict[str, Any]:
    """Return the standard invoice-total mismatch envelope."""
    return _build_result(
        ctx,
        "invoice_total_vs_line_items",
        "invoice",
        total_value,
        "invoice",
        compared_value,
        ValidationStatus.CRITICAL_MISMATCH,
        reason,
    )


def _coerce_line_item_number(value: Any, *, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Line item missing {field_name}.")
    return float(value)


def _validate_invoice_total_vs_line_items(
    ctx: ToolContext,
    tolerance: float,
) -> dict[str, Any]:
    """Data Models §5 `invoice_total_vs_line_items` with §6 monetary tolerance."""
    inv = ctx.extracted_fields.get("invoice")
    if not isinstance(inv, dict):
        return _invoice_total_line_items_error(
            ctx,
            None,
            None,
            "Invoice extracted_fields missing or invalid.",
        )
    total_value = inv.get("total_value")
    items = inv.get("line_items")
    if total_value is None or items is _MISSING or not isinstance(items, list):
        return _invoice_total_line_items_error(
            ctx,
            total_value,
            None,
            "Missing total_value or line_items on invoice.",
        )
    line_sum = 0.0
    for row in items:
        if not isinstance(row, dict):
            continue
        try:
            quantity = _coerce_line_item_number(row.get("quantity"), field_name="quantity")
            unit_price = _coerce_line_item_number(row.get("unit_price"), field_name="unit_price")
            line_sum += quantity * unit_price
        except (TypeError, ValueError, ArithmeticError) as exc:
            return _invoice_total_line_items_error(
                ctx,
                total_value,
                line_sum,
                f"Could not sum line items: {exc}",
            )
    try:
        diff = abs(float(total_value) - float(line_sum))
    except (TypeError, ValueError, ArithmeticError) as exc:
        return _invoice_total_line_items_error(
            ctx,
            total_value,
            line_sum,
            f"Invalid numeric total_value: {exc}",
        )
    if diff <= tolerance:
        return _build_result(
            ctx,
            "invoice_total_vs_line_items",
            "invoice",
            total_value,
            "invoice",
            line_sum,
            ValidationStatus.MATCH,
            f"|total_value - sum(qty*unit_price)| = {diff:g} <= tolerance {tolerance:g}.",
        )
    return _build_result(
        ctx,
        "invoice_total_vs_line_items",
        "invoice",
        total_value,
        "invoice",
        line_sum,
        ValidationStatus.CRITICAL_MISMATCH,
        f"|total_value - sum(qty*unit_price)| = {diff:g} > tolerance {tolerance:g}.",
    )


def _build_result(  # noqa: PLR0913 — positional construction keeps call sites compact
    ctx: ToolContext,
    field_name: str,
    doc_a: str,
    val_a: Any,
    doc_b: str,
    val_b: Any,
    status: ValidationStatus,
    reason: str,
) -> dict[str, Any]:
    result = ValidationResult(
        field=field_name,
        doc_a=doc_a,
        val_a=val_a,
        doc_b=doc_b,
        val_b=val_b,
        status=status,
        reason=reason,
    ).model_dump(mode="json")
    ctx.validations.append(result)
    return result


# ---- 1. validate_field_match --------------------------------------------


def validate_field_match(  # noqa: PLR0911, PLR0913
    ctx: ToolContext,
    field: str,
    doc_a: DocType,
    doc_b: DocType,
    tolerance: float = 0.0,
    peer_field: str | None = None,
) -> dict[str, Any]:
    """
    Compare the same canonical field across two documents using exact or
    tolerance-based matching. Use for numeric fields (weights, quantities,
    monetary values) and exact-string fields (incoterm, currency codes).
    Returns a ValidationResult dict; appends to exceptions if mismatch.
    """
    _validate_doc_keys(doc_a, doc_b)

    if field == "total_quantity":
        return _validate_total_quantity_match(ctx, doc_a, doc_b)
    if field == "invoice_total_vs_line_items":
        return _validate_invoice_total_vs_line_items(ctx, tolerance)

    field_b = peer_field or field
    val_a = _get_field(ctx.extracted_fields, doc_a, field)
    val_b = _get_field(ctx.extracted_fields, doc_b, field_b)

    if val_a is _MISSING:
        return _build_result(
            ctx,
            field,
            doc_a,
            None,
            doc_b,
            val_b if val_b is not _MISSING else None,
            ValidationStatus.CRITICAL_MISMATCH,
            f"Field '{field}' missing from {doc_a}",
        )
    if val_b is _MISSING:
        return _build_result(
            ctx,
            field,
            doc_a,
            val_a,
            doc_b,
            None,
            ValidationStatus.CRITICAL_MISMATCH,
            f"Field '{field}' missing from {doc_b}",
        )

    numeric_types = (int, float)
    a_is_num = isinstance(val_a, numeric_types) and not isinstance(val_a, bool)
    b_is_num = isinstance(val_b, numeric_types) and not isinstance(val_b, bool)

    if a_is_num and b_is_num:
        try:
            diff = abs(float(val_a) - float(val_b))
        except (ArithmeticError, OverflowError, ValueError) as exc:
            return _build_result(
                ctx,
                field,
                doc_a,
                val_a,
                doc_b,
                val_b,
                ValidationStatus.CRITICAL_MISMATCH,
                f"Numeric overflow during tolerance comparison: {exc}",
            )
        if diff <= tolerance:
            return _build_result(
                ctx,
                field,
                doc_a,
                val_a,
                doc_b,
                val_b,
                ValidationStatus.MATCH,
                f"|{val_a} - {val_b}| = {diff:g} <= tolerance {tolerance:g}",
            )
        return _build_result(
            ctx,
            field,
            doc_a,
            val_a,
            doc_b,
            val_b,
            ValidationStatus.CRITICAL_MISMATCH,
            f"|{val_a} - {val_b}| = {diff:g} > tolerance {tolerance:g}",
        )

    if isinstance(val_a, str) and isinstance(val_b, str):
        norm_a = val_a.strip().upper()
        norm_b = val_b.strip().upper()
        if norm_a == norm_b:
            return _build_result(
                ctx,
                field,
                doc_a,
                val_a,
                doc_b,
                val_b,
                ValidationStatus.MATCH,
                "Strings match (case-insensitive, trimmed).",
            )
        return _build_result(
            ctx,
            field,
            doc_a,
            val_a,
            doc_b,
            val_b,
            ValidationStatus.CRITICAL_MISMATCH,
            f"Strings differ: '{norm_a}' vs '{norm_b}'.",
        )

    if isinstance(val_a, list) and isinstance(val_b, list):
        set_a = {str(x) for x in val_a}
        set_b = {str(x) for x in val_b}
        if set_a == set_b:
            return _build_result(
                ctx,
                field,
                doc_a,
                val_a,
                doc_b,
                val_b,
                ValidationStatus.MATCH,
                "Lists are equal as sets.",
            )
        only_a = set_a - set_b
        only_b = set_b - set_a
        reason = (
            f"Set membership differs: only in {doc_a}={sorted(only_a)}, "
            f"only in {doc_b}={sorted(only_b)}."
        )
        return _build_result(
            ctx,
            field,
            doc_a,
            val_a,
            doc_b,
            val_b,
            ValidationStatus.CRITICAL_MISMATCH,
            reason,
        )

    # Type mismatch — raised per Error Handling §4.1; the dispatcher catches.
    raise ValueError(
        f"Cannot compare values of types {type(val_a).__name__} and "
        f"{type(val_b).__name__} for field '{field}'.",
    )


# ---- 2. validate_field_semantic -----------------------------------------


class _SemanticResponse(BaseModel):
    """Schema the semantic validator prompt returns.

    Only `status` and `reason` come from Gemini; the tool fills in `field`,
    `doc_a`, `val_a`, `doc_b`, `val_b` from its own arguments.
    """

    status: ValidationStatus
    reason: str


async def validate_field_semantic(
    ctx: ToolContext,
    field: str,
    doc_a: DocType,
    doc_b: DocType,
) -> dict[str, Any]:
    """
    Compare two string fields that may differ in formatting but be
    semantically equivalent (e.g. 'Acme Exports Ltd' vs 'ACME Exports
    Private Limited'). Uses a focused Gemini call with a rubric prompt.
    Returns ValidationResult dict.
    """
    _validate_doc_keys(doc_a, doc_b)

    canonical_field = field
    prompt_doc_a = doc_a
    prompt_doc_b = doc_b
    if field == "shipper_seller":
        val_a = _get_field(ctx.extracted_fields, "bol", "shipper")
        val_b = _get_field(ctx.extracted_fields, "invoice", "seller")
        canonical_field = "shipper_seller"
        prompt_doc_a, prompt_doc_b = "bol", "invoice"
    elif field == "consignee_buyer":
        val_a = _get_field(ctx.extracted_fields, "bol", "consignee")
        val_b = _get_field(ctx.extracted_fields, "invoice", "buyer")
        canonical_field = "consignee_buyer"
        prompt_doc_a, prompt_doc_b = "bol", "invoice"
    elif field == "description_of_goods":
        val_a = _get_field(ctx.extracted_fields, "bol", "description_of_goods")
        val_b = _first_invoice_line_description(ctx)
        canonical_field = "description_of_goods"
        prompt_doc_a, prompt_doc_b = "bol", "invoice"
    elif field == "currency_seller_plausibility":
        val_a = _get_field(ctx.extracted_fields, "invoice", "currency")
        val_b = _get_field(ctx.extracted_fields, "invoice", "seller")
        canonical_field = "currency_seller_plausibility"
        prompt_doc_a, prompt_doc_b = "invoice", "invoice"
    else:
        val_a = _get_field(ctx.extracted_fields, doc_a, field)
        val_b = _get_field(ctx.extracted_fields, doc_b, field)

    if val_a is _MISSING or val_b is _MISSING:
        if field in {"shipper_seller", "consignee_buyer", "description_of_goods"}:
            missing_doc = "bol" if val_a is _MISSING else "invoice"
        elif field == "currency_seller_plausibility":
            missing_doc = "invoice"
        else:
            missing_doc = doc_a if val_a is _MISSING else doc_b
        return _build_result(
            ctx,
            canonical_field,
            prompt_doc_a,
            None if val_a is _MISSING else val_a,
            prompt_doc_b,
            None if val_b is _MISSING else val_b,
            ValidationStatus.CRITICAL_MISMATCH,
            f"Field '{canonical_field}' missing from {missing_doc}.",
        )

    parsed, tokens = await gemini.call_gemini(
        prompt_name="semantic_validator",
        prompt_template=prompts.SEMANTIC_VALIDATOR_PROMPT,
        template_vars={
            "field_name": canonical_field,
            "doc_a": prompt_doc_a,
            "value_a": val_a,
            "doc_b": prompt_doc_b,
            "value_b": val_b,
        },
        response_schema=_SemanticResponse,
    )
    ctx.tokens_used += tokens

    out_status = parsed.status
    out_reason = parsed.reason
    if (
        canonical_field == "currency_seller_plausibility"
        and out_status == ValidationStatus.CRITICAL_MISMATCH
    ):
        out_status = ValidationStatus.MINOR_MISMATCH
        out_reason = (
            f"{out_reason} (currency vs seller heuristic is advisory per Data Models §5; "
            "never escalated to critical.)"
        )

    return _build_result(
        ctx,
        canonical_field,
        prompt_doc_a,
        val_a,
        prompt_doc_b,
        val_b,
        out_status,
        out_reason,
    )


# ---- 3. re_extract_field ------------------------------------------------


async def re_extract_field(
    ctx: ToolContext,
    doc_type: DocType,
    field: str,
    hint: str,
) -> dict[str, Any]:
    """
    Re-run extraction for a single field with a narrower prompt and a
    focus hint (e.g. 'look for a line starting with "Gross Weight"').
    Use when extraction_confidence for this field is < 0.7. Updates
    extracted_fields and extraction_confidence on success.
    """
    _validate_doc_keys(doc_type)
    if field == "line_items":
        raise ToolArgsValidationError(
            "ToolArgsValidationError: re_extract_field does not support line_items.",
            field=field,
        )

    raw_text = ctx.raw_texts.get(doc_type, "")
    prev_conf = ctx.extraction_confidence.get(doc_type, {}).get(field, {})
    previous_value = prev_conf.get("value")
    previous_confidence = prev_conf.get("confidence", 0.0)
    previous_rationale = prev_conf.get("rationale", "")

    schema = re_extraction_response_schema(field)
    parsed, tokens = await gemini.call_gemini(
        prompt_name="re_extraction",
        prompt_template=prompts.RE_EXTRACTION_PROMPT,
        template_vars={
            "doc_type": doc_type,
            "field_name": field,
            "previous_value": previous_value,
            "previous_confidence": previous_confidence,
            "previous_rationale": previous_rationale or "(none)",
            "hint": hint,
            "isolation_clause": prompts.ISOLATION_CLAUSE,
            "type_upper": doc_type.upper(),
            "raw_text": raw_text,
        },
        response_schema=schema,
    )
    ctx.tokens_used += tokens

    value, confidence, rationale = re_extraction_parsed_to_entry(parsed)

    # On success, mutate extracted_fields + extraction_confidence.
    ctx.extracted_fields.setdefault(doc_type, {})[field] = value
    ctx.extraction_confidence.setdefault(doc_type, {})[field] = {
        "field": field,
        "value": value,
        "confidence": confidence,
        "rationale": rationale,
    }

    return {
        "doc_type": doc_type,
        "field": field,
        "value": value,
        "confidence": confidence,
        "rationale": rationale,
    }


# ---- 4. check_container_consistency --------------------------------------


def check_container_consistency(ctx: ToolContext) -> dict[str, Any]:
    """
    Verify that the set of container numbers on the Bill of Lading
    matches the set on the Packing List (order-insensitive).
    """
    bol_containers = _get_field(ctx.extracted_fields, "bol", "container_numbers")
    pl_containers = _get_field(ctx.extracted_fields, "packing_list", "container_numbers")

    if bol_containers is _MISSING or not isinstance(bol_containers, list):
        pl_val = pl_containers if pl_containers is not _MISSING else None
        return _build_result(
            ctx,
            "container_numbers",
            "bol",
            None,
            "packing_list",
            pl_val,
            ValidationStatus.CRITICAL_MISMATCH,
            "Required field container_numbers missing or not a list on BoL.",
        )
    if pl_containers is _MISSING or not isinstance(pl_containers, list):
        return _build_result(
            ctx,
            "container_numbers",
            "bol",
            bol_containers,
            "packing_list",
            None,
            ValidationStatus.CRITICAL_MISMATCH,
            "Required field container_numbers missing or not a list on packing_list.",
        )

    set_bol = {str(x).strip().upper() for x in bol_containers}
    set_pl = {str(x).strip().upper() for x in pl_containers}

    if set_bol == set_pl:
        return _build_result(
            ctx,
            "container_numbers",
            "bol",
            bol_containers,
            "packing_list",
            pl_containers,
            ValidationStatus.MATCH,
            f"Container sets match ({len(set_bol)} containers).",
        )

    only_bol = sorted(set_bol - set_pl)
    only_pl = sorted(set_pl - set_bol)
    reason = f"Container sets differ. Only in BoL: {only_bol}. Only in Packing List: {only_pl}."
    return _build_result(
        ctx,
        "container_numbers",
        "bol",
        bol_containers,
        "packing_list",
        pl_containers,
        ValidationStatus.CRITICAL_MISMATCH,
        reason,
    )


# ---- 5. check_incoterm_port_plausibility --------------------------------


_CIF_LIKE = {"CIF", "CIP", "CFR", "CPT"}
_FOB_LIKE = {"FOB", "FCA", "FAS"}
_EXW_LIKE = {"EXW"}


def check_incoterm_port_plausibility(  # noqa: PLR0911 — one return per domain outcome
    ctx: ToolContext,
) -> dict[str, Any]:
    """
    Apply domain rules: EXW shouldn't appear with CIF-like freight charges;
    CIF/CIP require a destination port matching BoL port_of_discharge;
    FOB requires an origin port matching BoL port_of_loading.
    """
    invoice_incoterm = _get_field(ctx.extracted_fields, "invoice", "incoterm")
    port_of_loading = _get_field(ctx.extracted_fields, "bol", "port_of_loading")
    port_of_discharge = _get_field(ctx.extracted_fields, "bol", "port_of_discharge")

    if invoice_incoterm is _MISSING or not isinstance(invoice_incoterm, str):
        return _build_result(
            ctx,
            "incoterm_port_plausibility",
            "invoice",
            None,
            "bol",
            None,
            ValidationStatus.CRITICAL_MISMATCH,
            "Required field incoterm missing from invoice.",
        )

    incoterm = invoice_incoterm.strip().upper()
    loading = _nullable(port_of_loading)
    discharge = _nullable(port_of_discharge)

    if incoterm in _CIF_LIKE:
        if not isinstance(discharge, str) or not discharge.strip():
            reason = (
                f"Incoterm {incoterm} requires a named destination port; "
                "BoL port_of_discharge is missing."
            )
            return _build_result(
                ctx,
                "incoterm_port_plausibility",
                "invoice",
                incoterm,
                "bol",
                discharge,
                ValidationStatus.CRITICAL_MISMATCH,
                reason,
            )
        return _build_result(
            ctx,
            "incoterm_port_plausibility",
            "invoice",
            incoterm,
            "bol",
            discharge,
            ValidationStatus.MATCH,
            f"Incoterm {incoterm} consistent with named destination port '{discharge}'.",
        )

    if incoterm in _FOB_LIKE:
        if not isinstance(loading, str) or not loading.strip():
            reason = (
                f"Incoterm {incoterm} requires a named origin port; BoL port_of_loading is missing."
            )
            return _build_result(
                ctx,
                "incoterm_port_plausibility",
                "invoice",
                incoterm,
                "bol",
                loading,
                ValidationStatus.CRITICAL_MISMATCH,
                reason,
            )
        return _build_result(
            ctx,
            "incoterm_port_plausibility",
            "invoice",
            incoterm,
            "bol",
            loading,
            ValidationStatus.MATCH,
            f"Incoterm {incoterm} consistent with named origin port '{loading}'.",
        )

    if incoterm in _EXW_LIKE:
        # EXW: buyer takes over at origin. The domain concern is freight
        # charges appearing on the invoice — out of scope for M3's tool
        # implementation. Return MATCH with a note; the planner can
        # cross-check against invoice line items separately.
        return _build_result(
            ctx,
            "incoterm_port_plausibility",
            "invoice",
            incoterm,
            "bol",
            loading,
            ValidationStatus.MATCH,
            "EXW recorded; detailed freight-charge check not performed in deterministic tool.",
        )

    reason = (
        f"Incoterm '{incoterm}' is outside the CIF/FOB/EXW domain rules; "
        "skipping plausibility check."
    )
    return _build_result(
        ctx,
        "incoterm_port_plausibility",
        "invoice",
        incoterm,
        "bol",
        {"port_of_loading": loading, "port_of_discharge": discharge},
        ValidationStatus.MINOR_MISMATCH,
        reason,
    )


# ---- 6. check_container_number_format -----------------------------------


_ISO_6346_LETTER_VALUES: dict[str, int] = {
    "A": 10,
    "B": 12,
    "C": 13,
    "D": 14,
    "E": 15,
    "F": 16,
    "G": 17,
    "H": 18,
    "I": 19,
    "J": 20,
    "K": 21,
    "L": 23,
    "M": 24,
    "N": 25,
    "O": 26,
    "P": 27,
    "Q": 28,
    "R": 29,
    "S": 30,
    "T": 31,
    "U": 32,
    "V": 34,
    "W": 35,
    "X": 36,
    "Y": 37,
    "Z": 38,
}
_ISO_6346_PATTERN = re.compile(r"^[A-Z]{4}\d{7}$")
_ISO_6346_CHECK_WRAP = 10  # mod-11 remainder of 10 wraps to 0 per ISO 6346


def iso_6346_is_valid(container_number: str) -> bool:
    """Return True iff `container_number` is a valid ISO 6346 container ID.

    Format: strict 4 uppercase ASCII letters + 7 digits. Letters are
    converted to integers using the ISO 6346 table (A=10, B=12, ..., Z=38,
    skipping 11/22/33). Positions 0..9 are weighted by 2**i, summed, and
    reduced mod 11. A remainder of 10 wraps to 0; the result must equal the
    11th character treated as an integer.

    Lowercase, whitespace, hyphens, and any non-conforming length are
    rejected without attempting normalisation — a malformed container ID
    must surface as a finding for the planner.
    """
    if not isinstance(container_number, str):
        return False
    if not _ISO_6346_PATTERN.match(container_number):
        return False
    cn = container_number

    total = 0
    for i, ch in enumerate(cn[:10]):
        if ch.isalpha():
            total += _ISO_6346_LETTER_VALUES[ch] * (2**i)
        else:
            total += int(ch) * (2**i)

    check = total % 11
    if check == _ISO_6346_CHECK_WRAP:
        check = 0
    return check == int(cn[10])


_ISO_6346_REFERENCE_DOC = "iso_6346_spec"
_ISO_6346_REFERENCE_VAL = "4 letters + 7 digits with mod-11 check digit"


def check_container_number_format(ctx: ToolContext) -> dict[str, Any]:
    """
    Validate each container number against ISO 6346 format (4 letters +
    7 digits with mod-11 check digit). Purely programmatic, no LLM.

    This is a single-document sanity check, not a cross-document
    comparison — it produces `ExceptionRecord`s directly (severity
    ``warning`` per Data Models §5) rather than `ValidationResult`s. A
    bad check digit is almost always a transcription typo and must not
    dilute the ``critical`` severity that Data Models §5 reserves for
    inter-document contradictions.

    Behaviour:
    - Invalid container(s) found → one `ExceptionRecord` per bad number
      appended to `ctx.exceptions`.
    - All containers valid → no state mutation.
    - No container numbers available on either document → no state
      mutation; the planner decides whether to `escalate_to_human_review`.
    """
    bol_containers = _get_field(ctx.extracted_fields, "bol", "container_numbers")
    pl_containers = _get_field(ctx.extracted_fields, "packing_list", "container_numbers")

    all_numbers: list[tuple[str, str]] = []
    if isinstance(bol_containers, list):
        for cn in bol_containers:
            all_numbers.append(("bol", str(cn)))
    if isinstance(pl_containers, list):
        for cn in pl_containers:
            all_numbers.append(("packing_list", str(cn)))

    if not all_numbers:
        return {
            "ok": True,
            "checked": 0,
            "skipped": True,
            "reason": "No container numbers present on BoL or Packing List.",
            "created_exceptions": [],
        }

    invalid: list[tuple[str, str]] = [
        (doc, cn) for doc, cn in all_numbers if not iso_6346_is_valid(cn)
    ]

    if not invalid:
        return {
            "ok": True,
            "checked": len(all_numbers),
            "skipped": False,
            "reason": f"All {len(all_numbers)} container numbers pass ISO 6346 "
            "check-digit validation.",
            "created_exceptions": [],
        }

    created: list[dict[str, Any]] = []
    for doc, cn in invalid:
        record = ExceptionRecord(
            exception_id=str(uuid.uuid4()),
            severity=ExceptionSeverity.WARNING,
            field="container_number_format",
            description=(
                f"Container number {cn!r} on {doc} does not satisfy ISO 6346: "
                f"check digit is invalid. This is typically a transcription "
                f"typo; the document should be re-checked against the original."
            ),
            evidence=Evidence(
                doc_a=doc,
                val_a=cn,
                doc_b=_ISO_6346_REFERENCE_DOC,
                val_b=_ISO_6346_REFERENCE_VAL,
            ),
        )
        record_dict = record.model_dump(mode="json")
        ctx.exceptions.append(record_dict)
        created.append(record_dict)

    return {
        "ok": False,
        "checked": len(all_numbers),
        "skipped": False,
        "reason": f"{len(invalid)} of {len(all_numbers)} container numbers "
        "failed ISO 6346 check-digit validation.",
        "created_exceptions": created,
    }


# ---- 7. flag_exception --------------------------------------------------


class FlagEvidenceWire(BaseModel):
    """Structured evidence for ``flag_exception`` (Gemini-safe wire shape)."""

    doc_a: str
    doc_b: str
    val_a_json: str
    val_b_json: str


def flag_exception(
    ctx: ToolContext,
    severity: Literal["info", "warning", "critical"],
    field: str,
    description: str,
    evidence: FlagEvidenceWire,
) -> dict[str, Any]:
    """
    Record an exception. Only call this when a validation tool didn't
    already emit one — use for domain-level concerns the planner notices
    that don't fit a specific validation tool.
    """
    try:
        severity_enum = ExceptionSeverity(severity)
    except ValueError as exc:
        raise ToolArgsValidationError(
            f"ToolArgsValidationError: severity must be one of "
            f"{[s.value for s in ExceptionSeverity]}, got {severity!r}",
            severity=severity,
        ) from exc

    try:
        evidence_model = Evidence(
            doc_a=evidence.doc_a,
            doc_b=evidence.doc_b,
            val_a=parse_wire_json_value(evidence.val_a_json),
            val_b=parse_wire_json_value(evidence.val_b_json),
        )
    except (TypeError, ValueError) as exc:
        raise ToolArgsValidationError(
            f"ToolArgsValidationError: evidence shape invalid: {exc}",
            evidence=evidence,
        ) from exc

    record = ExceptionRecord(
        exception_id=str(uuid.uuid4()),
        severity=severity_enum,
        field=field,
        description=description,
        evidence=evidence_model,
    )
    record_dict = record.model_dump(mode="json")
    ctx.exceptions.append(record_dict)
    return record_dict


# ---- 8. escalate_to_human_review ----------------------------------------


def escalate_to_human_review(ctx: ToolContext, reason: str) -> dict[str, Any]:
    """
    Explicitly request human review. Call this when confidence is low
    across the board or when extracted fields are mutually inconsistent
    in a way the tools can't resolve. Sets needs_human_review=true.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ToolArgsValidationError(
            "ToolArgsValidationError: reason must be a non-empty string.",
        )
    ctx.needs_human_review = True
    ctx.review_reasons.append(reason.strip())
    return {
        "needs_human_review": True,
        "reason": reason.strip(),
        "total_reasons": len(ctx.review_reasons),
    }


# ---- LangChain tool schemas + registry (M3/M4) --------------------------


class EmptyArgs(BaseModel):
    """Tools that take no planner arguments beyond implicit context."""

    model_config = ConfigDict(extra="ignore")


class ValidateFieldMatchArgs(BaseModel):
    field: str
    doc_a: DocType
    doc_b: DocType
    tolerance: float = 0.0
    peer_field: str | None = None


class ValidateFieldSemanticArgs(BaseModel):
    field: str
    doc_a: DocType
    doc_b: DocType


class ReExtractFieldArgs(BaseModel):
    doc_type: DocType
    field: str
    hint: str


class FlagExceptionArgs(BaseModel):
    severity: Literal["info", "warning", "critical"]
    field: str
    description: str
    evidence: FlagEvidenceWire


class EscalateArgs(BaseModel):
    reason: str


def _sync_tool_stub(**_kwargs: Any) -> str:
    raise RuntimeError(
        "FreightCheck tools execute only via the dispatcher with ToolContext.",
    )


async def _async_tool_stub(**_kwargs: Any) -> str:
    raise RuntimeError(
        "FreightCheck tools execute only via the dispatcher with ToolContext.",
    )


TOOL_IMPLEMENTATIONS: dict[str, Callable[..., Any]] = {
    "validate_field_match": validate_field_match,
    "validate_field_semantic": validate_field_semantic,
    "re_extract_field": re_extract_field,
    "check_container_consistency": check_container_consistency,
    "check_incoterm_port_plausibility": check_incoterm_port_plausibility,
    "check_container_number_format": check_container_number_format,
    "flag_exception": flag_exception,
    "escalate_to_human_review": escalate_to_human_review,
}


def _structured_tool(
    *,
    name: str,
    description: str,
    args_schema: type[BaseModel],
    coroutine: Callable[..., Any] | None = None,
) -> StructuredTool:
    if coroutine is not None:
        return StructuredTool.from_function(
            coroutine=coroutine,
            name=name,
            description=description,
            args_schema=args_schema,
            infer_schema=False,
        )
    return StructuredTool.from_function(
        func=_sync_tool_stub,
        name=name,
        description=description,
        args_schema=args_schema,
        infer_schema=False,
    )


TOOL_REGISTRY: dict[str, StructuredTool] = {
    "validate_field_match": _structured_tool(
        name="validate_field_match",
        description=(validate_field_match.__doc__ or "").strip(),
        args_schema=ValidateFieldMatchArgs,
    ),
    "validate_field_semantic": _structured_tool(
        name="validate_field_semantic",
        description=(validate_field_semantic.__doc__ or "").strip(),
        args_schema=ValidateFieldSemanticArgs,
        coroutine=_async_tool_stub,
    ),
    "re_extract_field": _structured_tool(
        name="re_extract_field",
        description=(re_extract_field.__doc__ or "").strip(),
        args_schema=ReExtractFieldArgs,
        coroutine=_async_tool_stub,
    ),
    "check_container_consistency": _structured_tool(
        name="check_container_consistency",
        description=(check_container_consistency.__doc__ or "").strip(),
        args_schema=EmptyArgs,
    ),
    "check_incoterm_port_plausibility": _structured_tool(
        name="check_incoterm_port_plausibility",
        description=(check_incoterm_port_plausibility.__doc__ or "").strip(),
        args_schema=EmptyArgs,
    ),
    "check_container_number_format": _structured_tool(
        name="check_container_number_format",
        description=(check_container_number_format.__doc__ or "").strip(),
        args_schema=EmptyArgs,
    ),
    "flag_exception": _structured_tool(
        name="flag_exception",
        description=(flag_exception.__doc__ or "").strip(),
        args_schema=FlagExceptionArgs,
    ),
    "escalate_to_human_review": _structured_tool(
        name="escalate_to_human_review",
        description=(escalate_to_human_review.__doc__ or "").strip(),
        args_schema=EscalateArgs,
    ),
}


def build_planner_gemini_tools() -> list[Any]:
    """Convert registered tools to Gemini `Tool` function declarations."""
    decls: list[Any] = []
    for name in sorted(TOOL_REGISTRY.keys()):
        lc_tool = TOOL_REGISTRY[name]
        desc = (lc_tool.description or name).strip()
        args_schema = lc_tool.args_schema
        schema = (
            args_schema.model_json_schema()
            if isinstance(args_schema, type) and issubclass(args_schema, BaseModel)
            else {"type": "object", "properties": {}}
        )
        decls.append(
            genai_types.FunctionDeclaration(
                name=name,
                description=desc[:4096],
                parameters_json_schema=schema,
            ),
        )
    return [genai_types.Tool(function_declarations=decls)] if decls else []
