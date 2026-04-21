"""Smoke-run eval suites with Gemini mocked (no API key required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from eval.datasets import build_extraction_accuracy_dataset
from eval.suites.base import EvalContext
from eval.suites.extraction_accuracy import ExtractionAccuracySuite

from freightcheck.schemas.documents import BoLFields, InvoiceFields, LineItem, PackingListFields
from freightcheck.schemas.gemini_outputs import (
    BoLExtractionConfidencesGemini,
    BolExtractionGeminiResponse,
    FloatFieldConfidence,
    IntFieldConfidence,
    InvoiceExtractionConfidencesGemini,
    InvoiceExtractionGeminiResponse,
    LineItemsAggregateConfidence,
    PackingListExtractionConfidencesGemini,
    PackingListExtractionGeminiResponse,
    StrFieldConfidence,
    StrListFieldConfidence,
)


def _sc(value: str) -> StrFieldConfidence:
    return StrFieldConfidence(value=value, confidence=0.95)


def _stub_extractions() -> tuple[
    BolExtractionGeminiResponse,
    InvoiceExtractionGeminiResponse,
    PackingListExtractionGeminiResponse,
]:
    bol_f = BoLFields(
        bill_of_lading_number="BL1",
        shipper="S",
        consignee="C",
        vessel_name="V",
        port_of_loading="POL",
        port_of_discharge="POD",
        container_numbers=["MSCU1234567"],
        description_of_goods="goods",
        gross_weight=100.0,
        incoterm="FOB",
    )
    bol_c = BoLExtractionConfidencesGemini(
        bill_of_lading_number=_sc(bol_f.bill_of_lading_number),
        shipper=_sc(bol_f.shipper),
        consignee=_sc(bol_f.consignee),
        vessel_name=_sc(bol_f.vessel_name),
        port_of_loading=_sc(bol_f.port_of_loading),
        port_of_discharge=_sc(bol_f.port_of_discharge),
        container_numbers=StrListFieldConfidence(value=bol_f.container_numbers, confidence=0.95),
        description_of_goods=_sc(bol_f.description_of_goods),
        gross_weight=FloatFieldConfidence(value=bol_f.gross_weight, confidence=0.95),
        incoterm=_sc(bol_f.incoterm),
    )
    li = LineItem(description="x", quantity=1, unit_price=1.0)
    inv_f = InvoiceFields(
        invoice_number="INV1",
        seller="S",
        buyer="B",
        invoice_date="2026-01-01",
        line_items=[li],
        total_value=1.0,
        currency="USD",
        incoterm="FOB",
    )
    inv_c = InvoiceExtractionConfidencesGemini(
        invoice_number=_sc(inv_f.invoice_number),
        seller=_sc(inv_f.seller),
        buyer=_sc(inv_f.buyer),
        invoice_date=_sc(inv_f.invoice_date),
        line_items=LineItemsAggregateConfidence(confidence=0.95),
        total_value=FloatFieldConfidence(value=inv_f.total_value, confidence=0.95),
        currency=_sc(inv_f.currency),
        incoterm=_sc(inv_f.incoterm),
    )
    pli = LineItem(description="x", quantity=1, net_weight=100.0)
    pl_f = PackingListFields(
        total_packages=1,
        total_weight=100.0,
        container_numbers=["MSCU1234567"],
        line_items=[pli],
    )
    pl_c = PackingListExtractionConfidencesGemini(
        total_packages=IntFieldConfidence(value=pl_f.total_packages, confidence=0.95),
        total_weight=FloatFieldConfidence(value=pl_f.total_weight, confidence=0.95),
        container_numbers=StrListFieldConfidence(value=pl_f.container_numbers, confidence=0.95),
        line_items=LineItemsAggregateConfidence(confidence=0.95),
    )
    return (
        BolExtractionGeminiResponse(fields=bol_f, confidences=bol_c),
        InvoiceExtractionGeminiResponse(fields=inv_f, confidences=inv_c),
        PackingListExtractionGeminiResponse(fields=pl_f, confidences=pl_c),
    )


@pytest.mark.asyncio
async def test_extraction_accuracy_suite_produces_suite_result(tmp_path: Path) -> None:
    bol_p, inv_p, pl_p = _stub_extractions()

    async def fake_gemini(  # noqa: PLR0913
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        if prompt_name == "bol_extraction":
            return bol_p, 5
        if prompt_name == "invoice_extraction":
            return inv_p, 5
        if prompt_name == "packing_list_extraction":
            return pl_p, 5
        raise AssertionError(prompt_name)

    data = build_extraction_accuracy_dataset()[:1]
    ctx = EvalContext(output_dir=str(tmp_path))
    with patch("freightcheck.services.gemini.call_gemini", new=fake_gemini):
        suite = ExtractionAccuracySuite()
        result = await suite.run(data, ctx)
    assert result.suite == "extraction_accuracy"
    assert "field_accuracy" in result.metrics
    assert result.started_at
