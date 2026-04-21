"""Gemini-facing Pydantic models must not emit ``additionalProperties`` in JSON Schema."""

from __future__ import annotations

import json
from typing import TypeVar

import pytest
from pydantic import BaseModel

from freightcheck.agent.tools import FlagExceptionArgs, _SemanticResponse
from freightcheck.schemas.gemini_outputs import (
    BolExtractionGeminiResponse,
    InvoiceExtractionGeminiResponse,
    PackingListExtractionGeminiResponse,
    ReExtractFloatResult,
    ReExtractIntResult,
    ReExtractStringResult,
    ReExtractStrListResult,
)
from freightcheck.schemas.planner import PlannerLLMResponse

T = TypeVar("T", bound=BaseModel)

WIRE_MODELS: tuple[type[BaseModel], ...] = (
    BolExtractionGeminiResponse,
    InvoiceExtractionGeminiResponse,
    PackingListExtractionGeminiResponse,
    PlannerLLMResponse,
    ReExtractStringResult,
    ReExtractFloatResult,
    ReExtractIntResult,
    ReExtractStrListResult,
    FlagExceptionArgs,
    _SemanticResponse,
)


@pytest.mark.parametrize("model", WIRE_MODELS)
def test_model_json_schema_has_no_additional_properties(model: type[BaseModel]) -> None:
    blob = json.dumps(model.model_json_schema())
    assert "additionalProperties" not in blob, model.__name__
