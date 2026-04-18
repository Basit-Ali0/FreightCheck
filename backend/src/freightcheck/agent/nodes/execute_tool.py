# backend/src/freightcheck/agent/nodes/execute_tool.py
"""`execute_tool` node (LangGraph Flow Spec §2.3)."""

from __future__ import annotations

import copy
from time import perf_counter
from typing import Any

from freightcheck.agent.dispatcher import dispatch
from freightcheck.agent.state import AgentState
from freightcheck.agent.tools import ToolContext


async def execute_tool(state: AgentState) -> dict[str, Any]:
    """Drain `plan` FIFO; each tool appends to ctx accumulators."""
    if state.get("error"):
        return {}

    t0 = perf_counter()
    iteration = int(state.get("iteration_count", 0))
    plan = list(state.get("plan") or [])
    if not plan:
        return {"plan": [], "elapsed_ms": int((perf_counter() - t0) * 1000)}

    ctx = ToolContext(
        session_id=state["session_id"],
        extracted_fields=copy.deepcopy(state.get("extracted_fields", {})),
        extraction_confidence=copy.deepcopy(state.get("extraction_confidence", {})),
        raw_texts=dict(state.get("raw_texts", {})),
        validations=[],
        exceptions=[],
        needs_human_review=bool(state.get("needs_human_review", False)),
        review_reasons=[],
        tokens_used=0,
    )

    new_calls: list[dict[str, Any]] = []
    for item in plan:
        tool_name = str(item.get("tool_name", ""))
        raw_args = item.get("args")
        args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
        call_dict = await dispatch(tool_name, args, ctx, iteration)
        new_calls.append(call_dict)

    elapsed_ms = int((perf_counter() - t0) * 1000)

    out: dict[str, Any] = {
        "plan": [],
        "tool_calls": new_calls,
        "validations": ctx.validations,
        "exceptions": ctx.exceptions,
        "tokens_used": ctx.tokens_used,
        "elapsed_ms": elapsed_ms,
        "needs_human_review": ctx.needs_human_review,
    }
    if ctx.review_reasons:
        out["review_reasons"] = ctx.review_reasons
    if ctx.extracted_fields != state.get("extracted_fields"):
        out["extracted_fields"] = ctx.extracted_fields
    if ctx.extraction_confidence != state.get("extraction_confidence"):
        out["extraction_confidence"] = ctx.extraction_confidence
    return out
