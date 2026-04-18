# backend/src/freightcheck/schemas/documents.py
"""Document extraction Pydantic models per Data Models spec section 1.1 and 1.2."""

from typing import Any

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """A single line item within an invoice or packing list.

    `unit_price` is present in invoices, absent in packing lists.
    `net_weight` is present in packing lists, absent in invoices.
    """

    description: str
    quantity: int
    unit_price: float | None = None
    net_weight: float | None = None


class BoLFields(BaseModel):
    """Structured fields extracted from a Bill of Lading."""

    bill_of_lading_number: str
    shipper: str
    consignee: str
    vessel_name: str
    port_of_loading: str
    port_of_discharge: str
    container_numbers: list[str]
    description_of_goods: str
    gross_weight: float
    incoterm: str


class InvoiceFields(BaseModel):
    """Structured fields extracted from a Commercial Invoice."""

    invoice_number: str
    seller: str
    buyer: str
    invoice_date: str
    line_items: list[LineItem]
    total_value: float
    currency: str
    incoterm: str


class PackingListFields(BaseModel):
    """Structured fields extracted from a Packing List."""

    total_packages: int
    total_weight: float
    container_numbers: list[str]
    line_items: list[LineItem]


class ExtractionConfidence(BaseModel):
    """Per-field extraction confidence emitted by Gemini alongside the value.

    `rationale` is populated only when `confidence < 0.7` per Data Models
    section 1.2 confidence bands.
    """

    field: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class ExtractedDocument(BaseModel):
    """An extracted document carrying both structured fields and per-field confidences."""

    fields: BoLFields | InvoiceFields | PackingListFields
    confidences: dict[str, ExtractionConfidence]
