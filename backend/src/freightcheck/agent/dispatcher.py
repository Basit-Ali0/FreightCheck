# backend/src/freightcheck/agent/dispatcher.py
"""Single funnel for tool invocations (LangGraph Flow Spec §5)."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from freightcheck.agent.tools import TOOL_IMPLEMENTATIONS, TOOL_REGISTRY, ToolContext
from freightcheck.schemas.agent import ToolCall


def _validate_args_with_tool_schema(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        raise KeyError(f"Unregistered tool name: {tool_name}")
    schema = tool.args_schema
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        return {}
    validated = schema.model_validate(args or {})
    return validated.model_dump()


def _failed_tool_call(
    *,
    tool_name: str,
    args: dict[str, Any],
    iteration: int,
    started_at: datetime,
    error: str,
) -> dict[str, Any]:
    completed = datetime.now(UTC)
    return ToolCall(
        tool_call_id=str(uuid4()),
        iteration=iteration,
        tool_name=tool_name,
        args=args,
        result=None,
        started_at=started_at,
        completed_at=completed,
        duration_ms=0,
        status="error",
        error=error,
    ).model_dump(mode="json")


async def dispatch(
    tool_name: str,
    args: dict[str, Any],
    ctx: ToolContext,
    iteration: int,
) -> dict[str, Any]:
    """Invoke one tool; never raises — failures become `ToolCall` dicts with status error."""
    started_at = datetime.now(UTC)
    t0 = perf_counter()
    if tool_name not in TOOL_REGISTRY:
        return _failed_tool_call(
            tool_name=tool_name,
            args=args,
            iteration=iteration,
            started_at=started_at,
            error=f"Unregistered tool name: {tool_name}",
        )

    try:
        validated = _validate_args_with_tool_schema(tool_name, args)
    except Exception as exc:
        return _failed_tool_call(
            tool_name=tool_name,
            args=args,
            iteration=iteration,
            started_at=started_at,
            error=f"{type(exc).__name__}: {exc}",
        )

    fn = TOOL_IMPLEMENTATIONS.get(tool_name)
    if fn is None:
        return _failed_tool_call(
            tool_name=tool_name,
            args=args,
            iteration=iteration,
            started_at=started_at,
            error=f"No implementation registered for tool: {tool_name}",
        )

    try:
        if inspect.iscoroutinefunction(fn):
            result: Any = await fn(ctx, **validated)
        else:
            result = fn(ctx, **validated)
        status = "success"
        err: str | None = None
    except Exception as exc:
        result = None
        status = "error"
        err = f"{type(exc).__name__}: {exc}"

    duration_ms = int((perf_counter() - t0) * 1000)
    completed_at = datetime.now(UTC)
    return ToolCall(
        tool_call_id=str(uuid4()),
        iteration=iteration,
        tool_name=tool_name,
        args=args,
        result=result,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        status=status,  # type: ignore[arg-type]
        error=err,
    ).model_dump(mode="json")
