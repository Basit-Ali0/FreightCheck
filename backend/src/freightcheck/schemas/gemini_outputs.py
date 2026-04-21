"""Structured-output models for Gemini API calls (no ``dict[str, Any]`` / ``Any``).

The Gemini API rejects JSON Schema features such as ``additionalProperties``,
which Pydantic emits for ``dict[...]`` fields. These models are **wire-only**:
nodes translate into the existing session / persistence shapes after each call.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from freightcheck.schemas.documents import BoLFields, InvoiceFields, PackingListFields

# ---- Shared confidence leaf types -----------------------------------------


class StrFieldConfidence(BaseModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class FloatFieldConfidence(BaseModel):
    value: float
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class IntFieldConfidence(BaseModel):
    value: int
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class StrListFieldConfidence(BaseModel):
    value: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class LineItemsAggregateConfidence(BaseModel):
    """Single confidence for the ``line_items`` array (not per-row)."""

    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


BolConfEntry = tuple[str, StrFieldConfidence | FloatFieldConfidence | StrListFieldConfidence]

# ---- Extraction responses --------------------------------------------------


class BoLExtractionConfidencesGemini(BaseModel):
    bill_of_lading_number: StrFieldConfidence
    shipper: StrFieldConfidence
    consignee: StrFieldConfidence
    vessel_name: StrFieldConfidence
    port_of_loading: StrFieldConfidence
    port_of_discharge: StrFieldConfidence
    container_numbers: StrListFieldConfidence
    description_of_goods: StrFieldConfidence
    gross_weight: FloatFieldConfidence
    incoterm: StrFieldConfidence


class BolExtractionGeminiResponse(BaseModel):
    fields: BoLFields
    confidences: BoLExtractionConfidencesGemini


class InvoiceExtractionConfidencesGemini(BaseModel):
    invoice_number: StrFieldConfidence
    seller: StrFieldConfidence
    buyer: StrFieldConfidence
    invoice_date: StrFieldConfidence
    line_items: LineItemsAggregateConfidence
    total_value: FloatFieldConfidence
    currency: StrFieldConfidence
    incoterm: StrFieldConfidence


class InvoiceExtractionGeminiResponse(BaseModel):
    fields: InvoiceFields
    confidences: InvoiceExtractionConfidencesGemini


class PackingListExtractionConfidencesGemini(BaseModel):
    total_packages: IntFieldConfidence
    total_weight: FloatFieldConfidence
    container_numbers: StrListFieldConfidence
    line_items: LineItemsAggregateConfidence


class PackingListExtractionGeminiResponse(BaseModel):
    fields: PackingListFields
    confidences: PackingListExtractionConfidencesGemini


def bol_confidences_to_state_map(resp: BolExtractionGeminiResponse) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    c = resp.confidences
    mapping: list[BolConfEntry] = [
        ("bill_of_lading_number", c.bill_of_lading_number),
        ("shipper", c.shipper),
        ("consignee", c.consignee),
        ("vessel_name", c.vessel_name),
        ("port_of_loading", c.port_of_loading),
        ("port_of_discharge", c.port_of_discharge),
        ("container_numbers", c.container_numbers),
        ("description_of_goods", c.description_of_goods),
        ("gross_weight", c.gross_weight),
        ("incoterm", c.incoterm),
    ]
    for name, entry in mapping:
        out[name] = {
            "field": name,
            "value": entry.value,
            "confidence": entry.confidence,
            "rationale": entry.rationale,
        }
    return out


def invoice_confidences_to_state_map(
    resp: InvoiceExtractionGeminiResponse,
) -> dict[str, dict[str, Any]]:
    c = resp.confidences
    f = resp.fields
    out: dict[str, dict[str, Any]] = {}
    for name, entry in [
        ("invoice_number", c.invoice_number),
        ("seller", c.seller),
        ("buyer", c.buyer),
        ("invoice_date", c.invoice_date),
        ("total_value", c.total_value),
        ("currency", c.currency),
        ("incoterm", c.incoterm),
    ]:
        out[name] = {
            "field": name,
            "value": getattr(entry, "value", None),
            "confidence": getattr(entry, "confidence", 0.0),
            "rationale": getattr(entry, "rationale", ""),
        }
    agg = c.line_items
    out["line_items"] = {
        "field": "line_items",
        "value": [row.model_dump(mode="json") for row in f.line_items],
        "confidence": agg.confidence,
        "rationale": agg.rationale,
    }
    return out


def packing_list_confidences_to_state_map(
    resp: PackingListExtractionGeminiResponse,
) -> dict[str, dict[str, Any]]:
    c = resp.confidences
    f = resp.fields
    out: dict[str, dict[str, Any]] = {}
    for name, entry in [
        ("total_packages", c.total_packages),
        ("total_weight", c.total_weight),
        ("container_numbers", c.container_numbers),
    ]:
        out[name] = {
            "field": name,
            "value": getattr(entry, "value", None),
            "confidence": getattr(entry, "confidence", 0.0),
            "rationale": getattr(entry, "rationale", ""),
        }
    agg = c.line_items
    out["line_items"] = {
        "field": "line_items",
        "value": [row.model_dump(mode="json") for row in f.line_items],
        "confidence": agg.confidence,
        "rationale": agg.rationale,
    }
    return out


# ---- Re-extraction (field-typed, no ``Any``) -------------------------------


class ReExtractStringResult(BaseModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class ReExtractFloatResult(BaseModel):
    value: float
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class ReExtractIntResult(BaseModel):
    value: int
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class ReExtractStrListResult(BaseModel):
    value: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


_RE_FLOAT = frozenset({"gross_weight", "total_weight", "total_value"})
_RE_INT = frozenset({"total_packages"})
_RE_STR_LIST = frozenset({"container_numbers"})


def re_extraction_response_schema(field: str) -> type[BaseModel]:
    if field in _RE_FLOAT:
        return ReExtractFloatResult
    if field in _RE_INT:
        return ReExtractIntResult
    if field in _RE_STR_LIST:
        return ReExtractStrListResult
    return ReExtractStringResult


def re_extraction_parsed_to_entry(parsed: BaseModel) -> tuple[object, float, str | None]:
    if isinstance(parsed, ReExtractFloatResult):
        return parsed.value, parsed.confidence, parsed.rationale
    if isinstance(parsed, ReExtractIntResult):
        return parsed.value, parsed.confidence, parsed.rationale
    if isinstance(parsed, ReExtractStrListResult):
        return parsed.value, parsed.confidence, parsed.rationale
    if isinstance(parsed, ReExtractStringResult):
        return parsed.value, parsed.confidence, parsed.rationale
    raise TypeError(f"unexpected re-extraction model: {type(parsed).__name__}")


# ---- Planner (fixed invocation surface) -----------------------------------

DocTypeWire = Literal["bol", "invoice", "packing_list"]


class PlannerToolInvocation(BaseModel):
    """One tool call from the planner LLM (Gemini-safe: no open ``args`` dict)."""

    name: str
    field: str | None = None
    doc_a: DocTypeWire | None = None
    doc_b: DocTypeWire | None = None
    tolerance: float | None = None
    peer_field: str | None = None
    doc_type: DocTypeWire | None = None
    hint: str | None = None
    severity: Literal["info", "warning", "critical"] | None = None
    description: str | None = None
    reason: str | None = None
    evidence_doc_a: str | None = None
    evidence_doc_b: str | None = None
    evidence_val_a_json: str | None = None
    evidence_val_b_json: str | None = None


class PlannerLLMResponse(BaseModel):
    chosen_tools: list[PlannerToolInvocation] = Field(default_factory=list)
    rationale: str = ""
    terminate: bool = False


def parse_wire_json_value(blob: str | None) -> object:
    """Parse JSON text from planner wire fields; fall back to raw string."""
    if blob is None or blob == "":
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return blob


def planner_invocation_to_args(tool_name: str, inv: PlannerToolInvocation) -> dict[str, Any]:
    """Map the fixed planner invocation into per-tool ``args`` dicts for ``execute_tool``."""
    result: dict[str, Any] = {}
    if tool_name == "validate_field_match":
        if inv.field is not None and inv.doc_a is not None and inv.doc_b is not None:
            result = {
                "field": inv.field,
                "doc_a": inv.doc_a,
                "doc_b": inv.doc_b,
                "tolerance": 0.0 if inv.tolerance is None else inv.tolerance,
            }
            if inv.peer_field is not None:
                result["peer_field"] = inv.peer_field
    elif tool_name == "validate_field_semantic":
        if inv.field is not None and inv.doc_a is not None and inv.doc_b is not None:
            result = {"field": inv.field, "doc_a": inv.doc_a, "doc_b": inv.doc_b}
    elif tool_name == "re_extract_field":
        if inv.doc_type is not None and inv.field is not None and inv.hint is not None:
            result = {"doc_type": inv.doc_type, "field": inv.field, "hint": inv.hint}
    elif tool_name == "flag_exception":
        if (
            inv.severity is not None
            and inv.field is not None
            and inv.description is not None
            and inv.evidence_doc_a is not None
            and inv.evidence_doc_b is not None
            and inv.evidence_val_a_json is not None
            and inv.evidence_val_b_json is not None
        ):
            result = {
                "severity": inv.severity,
                "field": inv.field,
                "description": inv.description,
                "evidence": {
                    "doc_a": inv.evidence_doc_a,
                    "doc_b": inv.evidence_doc_b,
                    "val_a": parse_wire_json_value(inv.evidence_val_a_json),
                    "val_b": parse_wire_json_value(inv.evidence_val_b_json),
                },
            }
    elif tool_name == "escalate_to_human_review" and inv.reason is not None:
        result = {"reason": inv.reason}
    return result
