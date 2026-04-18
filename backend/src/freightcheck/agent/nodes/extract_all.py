# backend/src/freightcheck/agent/nodes/extract_all.py
"""`extract_all` node (LangGraph Flow Spec §2.1)."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

import structlog

from freightcheck.agent import prompts
from freightcheck.agent.state import AgentState
from freightcheck.errors import ExtractionError
from freightcheck.schemas.documents import (
    BolExtractionResponse,
    InvoiceExtractionResponse,
    PackingListExtractionResponse,
)
from freightcheck.services import gemini

log = structlog.get_logger()

# Data Models §1.2: confidence below this threshold flags `needs_human_review`.
_LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.5


def _confidence_dict(conf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field_name, c in conf.items():
        if hasattr(c, "model_dump"):
            out[field_name] = c.model_dump(mode="json")
        elif isinstance(c, dict):
            out[field_name] = dict(c)
    return out


async def extract_all(state: AgentState) -> dict[str, Any]:
    """Parallel Gemini extraction for BoL, invoice, and packing list."""
    if state.get("error"):
        return {}

    t0 = perf_counter()
    raw = state["raw_texts"]

    async def bol() -> tuple[BolExtractionResponse, int]:
        return await gemini.call_gemini(
            prompt_name="bol_extraction",
            prompt_template=prompts.BOL_EXTRACTION_PROMPT,
            template_vars={
                "isolation_clause": prompts.ISOLATION_CLAUSE,
                "raw_text": raw.get("bol", ""),
            },
            response_schema=BolExtractionResponse,
        )

    async def inv() -> tuple[InvoiceExtractionResponse, int]:
        return await gemini.call_gemini(
            prompt_name="invoice_extraction",
            prompt_template=prompts.INVOICE_EXTRACTION_PROMPT,
            template_vars={
                "isolation_clause": prompts.ISOLATION_CLAUSE,
                "raw_text": raw.get("invoice", ""),
            },
            response_schema=InvoiceExtractionResponse,
        )

    async def pl() -> tuple[PackingListExtractionResponse, int]:
        return await gemini.call_gemini(
            prompt_name="packing_list_extraction",
            prompt_template=prompts.PACKING_LIST_EXTRACTION_PROMPT,
            template_vars={
                "isolation_clause": prompts.ISOLATION_CLAUSE,
                "raw_text": raw.get("packing_list", ""),
            },
            response_schema=PackingListExtractionResponse,
        )

    try:
        (bol_p, bol_t), (inv_p, inv_t), (pl_p, pl_t) = await asyncio.gather(bol(), inv(), pl())
    except ExtractionError as exc:
        elapsed_ms = int((perf_counter() - t0) * 1000)
        log.warning("agent.extract_all_failed", error=str(exc))
        return {
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
            "status": "processing",
        }

    tokens_used = bol_t + inv_t + pl_t
    extracted_fields: dict[str, Any] = {
        "bol": bol_p.fields.model_dump(mode="json"),
        "invoice": inv_p.fields.model_dump(mode="json"),
        "packing_list": pl_p.fields.model_dump(mode="json"),
    }
    extraction_confidence: dict[str, dict[str, dict[str, Any]]] = {
        "bol": _confidence_dict(bol_p.confidences),
        "invoice": _confidence_dict(inv_p.confidences),
        "packing_list": _confidence_dict(pl_p.confidences),
    }

    needs_human_review = False
    review_reasons: list[str] = []
    for doc_key, conf_map in extraction_confidence.items():
        for field_name, meta in conf_map.items():
            conf = float(meta.get("confidence", 1.0))
            if conf < _LOW_CONFIDENCE_REVIEW_THRESHOLD:
                needs_human_review = True
                rationale = meta.get("rationale") or ""
                review_reasons.append(
                    f"{doc_key}.{field_name} extracted with confidence {conf:.2f}: {rationale}",
                )

    elapsed_ms = int((perf_counter() - t0) * 1000)
    log.info(
        "agent.extract_all_complete",
        session_id=state["session_id"],
        tokens_used=tokens_used,
        needs_human_review=needs_human_review,
    )
    return {
        "extracted_fields": extracted_fields,
        "extraction_confidence": extraction_confidence,
        "needs_human_review": needs_human_review,
        "review_reasons": review_reasons,
        "tokens_used": tokens_used,
        "elapsed_ms": elapsed_ms,
        "status": "processing",
    }
