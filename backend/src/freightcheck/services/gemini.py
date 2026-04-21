# backend/src/freightcheck/services/gemini.py
"""Gemini wrapper per Error Handling spec section 2.

This module is the only place in the codebase that touches the Google Gemini
SDK. Every call to the model — extraction, planner, semantic validator,
re-extraction, summary — goes through `call_gemini`. The wrapper handles:

- Network retries with exponential backoff on 429 / 5xx / timeout.
- Schema retries with corrective prompts on malformed JSON.
- Token accounting.
- Mapping `prompt_name` to the right FreightCheckError subclass on failure.
- Structured logging of every Gemini interaction.

Unit tests mock `_raw_gemini_call` so the retry behaviour can be exercised
without hitting the network; live integration tests (marked
`@pytest.mark.integration`) bypass the mock and hit the real API.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from freightcheck.agent import prompts
from freightcheck.errors import (
    ExtractionError,
    FreightCheckError,
    GeminiAPIError,
    PlannerError,
    SemanticValidationError,
)
from freightcheck.settings import settings

log = structlog.get_logger()


TModel = TypeVar("TModel", bound=BaseModel)


# Per Error Handling spec section 2.1: network retries are independent from
# schema retries. A single call may therefore consume up to
# `(_MAX_NETWORK_RETRIES + 1) * (_MAX_SCHEMA_RETRIES + 1)` roundtrips in the
# worst case.
_MAX_NETWORK_RETRIES = 2
_MAX_SCHEMA_RETRIES = 2


class RetryableGeminiError(Exception):
    """Marker raised by `_raw_gemini_call` for 429 / 5xx / timeout.

    The wrapper catches this and retries with backoff. Non-retryable HTTP
    failures (4xx other than 429, auth) should raise `GeminiAPIError`
    directly from the raw layer and skip the retry loop.
    """


def _exception_for_prompt(prompt_name: str) -> type[FreightCheckError]:
    """Map a prompt_name to the exception class raised on final schema failure.

    See Error Handling section 2.3.
    """
    if prompt_name == "planner":
        return PlannerError
    if prompt_name == "semantic_validator":
        return SemanticValidationError
    # bol_extraction / invoice_extraction / packing_list_extraction / re_extraction
    # and any unrecognised name default to ExtractionError.
    return ExtractionError


# HTTP status codes the wrapper treats as retryable network failures.
# 429 → rate-limit / quota; 5xx → transient service-side failures. Any other
# 4xx (auth, bad request, etc.) is non-retryable and surfaces as GeminiAPIError.
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


async def _raw_gemini_call(
    prompt: str,
    response_schema: type[BaseModel],
    tools: list[Any] | None = None,
    system_instruction: str = prompts.SYSTEM_INSTRUCTION,
) -> tuple[str, int]:
    """Execute a single Gemini generation request via the `google-genai` SDK.

    Returns
    -------
    (response_text, tokens_used)
        `response_text` is the raw JSON text the model produced (schema
        enforcement on the SDK side makes this valid JSON in the happy path).
        `tokens_used` is the prompt + candidates token total from the usage
        metadata. Callers sum these across retries.

    Raises
    ------
    RetryableGeminiError
        On HTTP 429, 5xx, or network timeout. The wrapper retries with
        backoff.
    GeminiAPIError
        On auth failure, 4xx other than 429, or any other non-retryable
        failure.

    Unit tests monkeypatch this function. Integration tests call it for real.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiAPIError(
            "GeminiAPIError: GEMINI_API_KEY is not configured. "
            "Set it in backend/.env or the deployment environment.",
        )

    try:
        # Lazy imports keep the unit-test surface SDK-free; see module docstring.
        from google import genai  # noqa: PLC0415
        from google.genai import errors as genai_errors  # noqa: PLC0415
        from google.genai import types as genai_types  # noqa: PLC0415
    except ImportError as exc:
        raise GeminiAPIError(
            f"GeminiAPIError: google-genai SDK not installed: {exc}",
        ) from exc

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Gemini does not allow response_mime_type / response_schema together
    # with function-calling tools.  When tools are present, omit the JSON
    # response constraints and let call_gemini validate the schema after
    # receiving the raw text.
    if tools:
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.0,
            tools=tools,
        )
    else:
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.0,
        )

    try:
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
    except genai_errors.ServerError as exc:  # 5xx
        raise RetryableGeminiError(str(exc)) from exc
    except genai_errors.ClientError as exc:  # 4xx
        if exc.code in _RETRYABLE_STATUS_CODES:  # 429
            raise RetryableGeminiError(str(exc)) from exc
        raise GeminiAPIError(f"GeminiAPIError: {exc}") from exc
    except genai_errors.APIError as exc:  # catch-all (unknown code, etc.)
        if exc.code in _RETRYABLE_STATUS_CODES:
            raise RetryableGeminiError(str(exc)) from exc
        raise GeminiAPIError(f"GeminiAPIError: {exc}") from exc
    except TimeoutError as exc:  # asyncio.wait_for timeouts etc.
        raise RetryableGeminiError(f"Gemini request timed out: {exc}") from exc

    usage = getattr(response, "usage_metadata", None)
    tokens_used = int(getattr(usage, "total_token_count", 0) or 0)

    if tools and getattr(response, "function_calls", None):
        import json  # noqa: PLC0415

        chosen_tools = [
            {"name": fc.name, **(fc.args or {})} for fc in (response.function_calls or [])
        ]
        parts = (
            response.candidates[0].content.parts
            if response.candidates and response.candidates[0].content
            else []
        )
        rationale = "\n".join(
            str(getattr(p, "text", "")) for p in (parts or []) if getattr(p, "text", None)
        ).strip()
        text = json.dumps(
            {
                "chosen_tools": chosen_tools,
                "rationale": rationale,
                "terminate": False,
            }
        )
    else:
        text = response.text or "" if hasattr(response, "text") else ""

    return text, tokens_used


async def call_gemini(  # noqa: PLR0913 — signature mandated by Error Handling §2.2
    prompt_name: str,
    prompt_template: str,
    template_vars: dict[str, Any],
    response_schema: type[TModel],
    tools: list[Any] | None = None,
    system_instruction: str = prompts.SYSTEM_INSTRUCTION,
) -> tuple[TModel, int]:
    """Call Gemini with retry and schema-correction handling.

    Parameters
    ----------
    prompt_name
        Canonical name of the prompt — "bol_extraction", "planner",
        "semantic_validator", etc. Drives log tagging and the final
        exception class.
    prompt_template
        The template string from `agent.prompts`. Formatted with
        `template_vars`. Never composed from user data outside
        `{isolation_clause}` / `{raw_text}` — see Prompt Templates section 1.
    template_vars
        Values filled into the template. Must include all named placeholders.
    response_schema
        A Pydantic `BaseModel` subclass. Passed to the SDK as the structured
        output schema and used to validate the response text.
    tools
        Optional list of tools bound to the model (planner-only in practice).
    system_instruction
        Defaults to the shared FreightCheck system instruction.

    Returns
    -------
    (parsed, tokens_used)
        `parsed` is a validated instance of `response_schema`. `tokens_used`
        is the cumulative token total across all network roundtrips the
        call consumed.

    Raises
    ------
    GeminiAPIError
        Network/auth/rate-limit failure after `_MAX_NETWORK_RETRIES` retries.
    ExtractionError / PlannerError / SemanticValidationError
        Schema-validation failure after `_MAX_SCHEMA_RETRIES` corrective
        attempts. Class is chosen by `prompt_name` per Error Handling §2.3.
    """
    prompt_version = prompts.PROMPT_VERSIONS.get(prompt_name, "unknown")
    exc_class = _exception_for_prompt(prompt_name)

    initial_prompt = prompt_template.format(**template_vars)
    current_prompt = initial_prompt
    total_tokens = 0
    last_validation_error: ValidationError | None = None

    for schema_attempt in range(_MAX_SCHEMA_RETRIES + 1):
        response_text: str | None = None
        for net_attempt in range(_MAX_NETWORK_RETRIES + 1):
            log.info(
                "agent.gemini_call",
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                schema_attempt=schema_attempt,
                net_attempt=net_attempt,
            )
            try:
                response_text, tokens = await _raw_gemini_call(
                    current_prompt,
                    response_schema,
                    tools=tools,
                    system_instruction=system_instruction,
                )
                total_tokens += tokens
                break
            except RetryableGeminiError as exc:
                if net_attempt < _MAX_NETWORK_RETRIES:
                    delay = 2.0 * (net_attempt + 1)
                    log.warning(
                        "agent.gemini_retry",
                        prompt_name=prompt_name,
                        reason="retryable_http_error",
                        detail=str(exc),
                        delay_seconds=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise GeminiAPIError(
                    f"GeminiAPIError: {prompt_name} failed after "
                    f"{_MAX_NETWORK_RETRIES} retries: {exc}",
                    prompt_name=prompt_name,
                ) from exc

        if response_text is None:  # pragma: no cover — loop invariant
            raise GeminiAPIError(
                f"GeminiAPIError: {prompt_name} produced no response.",
                prompt_name=prompt_name,
            )

        try:
            parsed = response_schema.model_validate_json(response_text)
        except ValidationError as ve:
            last_validation_error = ve
            if schema_attempt < _MAX_SCHEMA_RETRIES:
                truncated = str(ve)[:500]
                log.warning(
                    "agent.gemini_schema_retry",
                    prompt_name=prompt_name,
                    attempt=schema_attempt,
                    validation_error=truncated,
                )
                if schema_attempt == 0:
                    current_prompt = prompts.RETRY_SCHEMA_PROMPT.format(
                        validation_error=truncated,
                    )
                else:
                    current_prompt = prompts.RETRY_STRICT_PROMPT
                continue
            break
        else:
            log.info(
                "agent.gemini_call_success",
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                tokens_used=total_tokens,
            )
            return parsed, total_tokens

    message = (
        f"{exc_class.__name__}: {prompt_name} returned invalid JSON after "
        f"{_MAX_SCHEMA_RETRIES} schema retries. Last error: "
        f"{str(last_validation_error)[:300]}"
    )
    raise exc_class(message, prompt_name=prompt_name)
