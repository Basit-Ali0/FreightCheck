# backend/tests/unit/test_gemini.py
"""Unit tests for the Gemini wrapper covering retry, schema, and exception mapping."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pydantic import BaseModel

from freightcheck.agent import prompts
from freightcheck.errors import (
    ExtractionError,
    GeminiAPIError,
    PlannerError,
    SemanticValidationError,
)
from freightcheck.services import gemini
from tests.fixtures.gemini_responses import good_semantic_response


class _TinyResponse(BaseModel):
    status: str
    reason: str


def _script_raw_calls(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[tuple[str, int] | Exception],
    calls_log: list[dict[str, Any]] | None = None,
) -> None:
    """Monkeypatch `_raw_gemini_call` with a scripted FIFO response queue."""
    queue = list(responses)

    async def fake_raw_call(
        prompt: str,
        response_schema: type[BaseModel],
        tools: list[Any] | None = None,
        system_instruction: str = prompts.SYSTEM_INSTRUCTION,
    ) -> tuple[str, int]:
        if calls_log is not None:
            calls_log.append({"prompt": prompt})
        if not queue:
            raise AssertionError("No more scripted raw Gemini responses.")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(gemini, "_raw_gemini_call", fake_raw_call)


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neuter `asyncio.sleep` inside the wrapper so retry tests run instantly."""

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(gemini.asyncio, "sleep", fake_sleep)


async def test_call_gemini_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _script_raw_calls(
        monkeypatch,
        responses=[(good_semantic_response("match", "same entity"), 1234)],
    )

    parsed, tokens = await gemini.call_gemini(
        prompt_name="semantic_validator",
        prompt_template=prompts.SEMANTIC_VALIDATOR_PROMPT,
        template_vars={
            "field_name": "shipper",
            "doc_a": "bol",
            "value_a": "Acme",
            "doc_b": "invoice",
            "value_b": "ACME",
        },
        response_schema=_TinyResponse,
    )

    assert parsed.status == "match"
    assert parsed.reason == "same entity"
    assert tokens == 1234


async def test_call_gemini_retries_on_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """First response fails schema, second succeeds → returns second."""
    _no_sleep(monkeypatch)
    calls: list[dict[str, Any]] = []
    _script_raw_calls(
        monkeypatch,
        responses=[
            ('{"status": "match"}', 100),  # missing reason — schema fail
            (good_semantic_response("match", "ok"), 200),
        ],
        calls_log=calls,
    )

    parsed, tokens = await gemini.call_gemini(
        prompt_name="semantic_validator",
        prompt_template=prompts.SEMANTIC_VALIDATOR_PROMPT,
        template_vars={
            "field_name": "shipper",
            "doc_a": "bol",
            "value_a": "A",
            "doc_b": "invoice",
            "value_b": "B",
        },
        response_schema=_TinyResponse,
    )

    assert parsed.reason == "ok"
    assert tokens == 300
    assert len(calls) == 2
    assert "did not match the required JSON schema" in calls[1]["prompt"]


async def test_call_gemini_raises_after_two_schema_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three consecutive schema failures → ExtractionError (for extraction prompts)."""
    _no_sleep(monkeypatch)
    _script_raw_calls(
        monkeypatch,
        responses=[
            ('{"status": "match"}', 100),  # malformed #1
            ('{"status": "match"}', 100),  # malformed #2
            ('{"status": "match"}', 100),  # malformed #3
        ],
    )

    with pytest.raises(ExtractionError, match="bol_extraction"):
        await gemini.call_gemini(
            prompt_name="bol_extraction",
            prompt_template="ignored {a}",
            template_vars={"a": 1},
            response_schema=_TinyResponse,
        )


async def test_call_gemini_raises_planner_error_for_planner_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_sleep(monkeypatch)
    _script_raw_calls(
        monkeypatch,
        responses=[('{"status": "match"}', 10)] * 3,
    )

    with pytest.raises(PlannerError):
        await gemini.call_gemini(
            prompt_name="planner",
            prompt_template="ignored {a}",
            template_vars={"a": 1},
            response_schema=_TinyResponse,
        )


async def test_call_gemini_raises_semantic_error_for_semantic_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_sleep(monkeypatch)
    _script_raw_calls(
        monkeypatch,
        responses=[('{"status": "match"}', 10)] * 3,
    )

    with pytest.raises(SemanticValidationError):
        await gemini.call_gemini(
            prompt_name="semantic_validator",
            prompt_template="ignored {a}",
            template_vars={"a": 1},
            response_schema=_TinyResponse,
        )


async def test_call_gemini_retries_on_retryable_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call raises RetryableGeminiError (429-equivalent), second succeeds."""
    _no_sleep(monkeypatch)
    _script_raw_calls(
        monkeypatch,
        responses=[
            gemini.RetryableGeminiError("429 quota exceeded"),
            (good_semantic_response("match", "ok"), 500),
        ],
    )

    parsed, tokens = await gemini.call_gemini(
        prompt_name="semantic_validator",
        prompt_template=prompts.SEMANTIC_VALIDATOR_PROMPT,
        template_vars={
            "field_name": "f",
            "doc_a": "bol",
            "value_a": "a",
            "doc_b": "invoice",
            "value_b": "b",
        },
        response_schema=_TinyResponse,
    )

    assert parsed.status == "match"
    assert tokens == 500


async def test_call_gemini_raises_gemini_api_error_after_exhausted_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_sleep(monkeypatch)
    _script_raw_calls(
        monkeypatch,
        responses=[
            gemini.RetryableGeminiError("429 #1"),
            gemini.RetryableGeminiError("429 #2"),
            gemini.RetryableGeminiError("429 #3"),
        ],
    )

    with pytest.raises(GeminiAPIError, match="after 2 retries"):
        await gemini.call_gemini(
            prompt_name="semantic_validator",
            prompt_template="ignored {a}",
            template_vars={"a": 1},
            response_schema=_TinyResponse,
        )


async def test_call_gemini_propagates_non_retryable_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4xx / auth failures must propagate immediately — no retry."""
    attempts = 0
    _no_sleep(monkeypatch)

    async def fake_raw_call(*_args: object, **_kwargs: object) -> tuple[str, int]:
        nonlocal attempts
        attempts += 1
        raise GeminiAPIError("GeminiAPIError: 401 unauthorized")

    monkeypatch.setattr(gemini, "_raw_gemini_call", fake_raw_call)

    with pytest.raises(GeminiAPIError, match="401"):
        await gemini.call_gemini(
            prompt_name="semantic_validator",
            prompt_template="ignored {a}",
            template_vars={"a": 1},
            response_schema=_TinyResponse,
        )

    assert attempts == 1, "non-retryable errors must not be retried"


async def test_exception_for_prompt_mapping() -> None:
    """Every prompt_name maps to the correct FreightCheckError subclass."""
    assert gemini._exception_for_prompt("planner") is PlannerError
    assert gemini._exception_for_prompt("semantic_validator") is SemanticValidationError
    assert gemini._exception_for_prompt("bol_extraction") is ExtractionError
    assert gemini._exception_for_prompt("invoice_extraction") is ExtractionError
    assert gemini._exception_for_prompt("packing_list_extraction") is ExtractionError
    assert gemini._exception_for_prompt("re_extraction") is ExtractionError
    assert gemini._exception_for_prompt("unknown_prompt") is ExtractionError


# The shape of the monkeypatched function — purely for static clarity when
# reviewing this file.
FakeRawCall = Callable[..., Awaitable[tuple[str, int]]]
