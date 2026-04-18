# backend/src/freightcheck/agent/nodes/plan_validations.py
"""`plan_validations` node (LangGraph Flow Spec §2.2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

import structlog

from freightcheck.agent import prompts
from freightcheck.agent.state import AgentState
from freightcheck.agent.tools import TOOL_REGISTRY
from freightcheck.errors import PlannerError
from freightcheck.schemas.agent import PlannerDecision, ToolCall
from freightcheck.schemas.planner import PlannerLLMResponse
from freightcheck.services import gemini
from freightcheck.settings import settings

log = structlog.get_logger()


def _flatten_extracted(extracted: dict[str, Any], limit: int = 80) -> str:
    flat: dict[str, Any] = {}
    for doc, fields in extracted.items():
        if not isinstance(fields, dict):
            continue
        for k, v in fields.items():
            flat[f"{doc}.{k}"] = v
            if len(flat) >= limit:
                break
        if len(flat) >= limit:
            break
    return json.dumps(flat, default=str)[:4000]


def _confidence_rows(conf: dict[str, Any], top: int = 10) -> str:
    rows: list[tuple[float, str]] = []
    for doc, fields in conf.items():
        if not isinstance(fields, dict):
            continue
        for field_name, meta in fields.items():
            if not isinstance(meta, dict):
                continue
            c = float(meta.get("confidence", 1.0))
            rows.append((c, f"{doc}.{field_name}"))
    rows.sort(key=lambda x: x[0])
    slim = [{"field": f, "confidence": c} for c, f in rows[:top]]
    return json.dumps(slim, default=str)


def _validations_summary(vals: list[dict[str, Any]], limit: int = 20) -> str:
    slim = [{"field": v.get("field"), "status": v.get("status")} for v in vals[-limit:]]
    return json.dumps(slim, default=str)


def _exceptions_summary(excs: list[dict[str, Any]], limit: int = 15) -> str:
    slim = [{"field": e.get("field"), "severity": e.get("severity")} for e in excs[-limit:]]
    return json.dumps(slim, default=str)


def _prior_tool_calls(calls: list[dict[str, Any]], limit: int = 10) -> str:
    tail = calls[-limit:]
    slim: list[dict[str, Any]] = []
    for c in tail:
        res = c.get("result")
        res_summary = str(res)[:200] if res is not None else None
        slim.append(
            {
                "iteration": c.get("iteration"),
                "tool": c.get("tool_name"),
                "args": c.get("args"),
                "status": c.get("status"),
                "result_summary": res_summary,
            },
        )
    return json.dumps(slim, default=str)


async def plan_validations(state: AgentState) -> dict[str, Any]:
    """One planner Gemini call; fills `plan` and appends `PlannerDecision`."""
    if state.get("error"):
        return {}

    t0 = perf_counter()
    iteration_next = int(state.get("iteration_count", 0)) + 1
    remaining_iters = max(0, settings.AGENT_MAX_ITERATIONS - iteration_next)
    remaining_tokens = max(0, settings.AGENT_TOKEN_BUDGET - int(state.get("tokens_used", 0)))

    template_vars = {
        "iteration_count": state.get("iteration_count", 0),
        "remaining_iterations": remaining_iters,
        "remaining_tokens": remaining_tokens,
        "extracted_summary": _flatten_extracted(state.get("extracted_fields", {})),
        "confidence_summary": _confidence_rows(state.get("extraction_confidence", {})),
        "validations_summary": _validations_summary(state.get("validations", [])),
        "exceptions_summary": _exceptions_summary(state.get("exceptions", [])),
        "prior_tool_calls": _prior_tool_calls(state.get("tool_calls", [])),
    }

    synthetic_tool_calls: list[dict[str, Any]] = []
    try:
        parsed, tokens = await gemini.call_gemini(
            prompt_name="planner",
            prompt_template=prompts.PLANNER_PROMPT,
            template_vars=template_vars,
            response_schema=PlannerLLMResponse,
        )
    except PlannerError as exc:
        elapsed_ms = int((perf_counter() - t0) * 1000)
        log.warning("agent.planner_failed", error=str(exc))
        return {
            "error": str(exc),
            "tokens_used": 0,
            "elapsed_ms": elapsed_ms,
        }

    terminate = bool(parsed.terminate)
    chosen_names: list[str] = []
    plan_queue: list[dict[str, Any]] = []

    for inv in parsed.chosen_tools:
        name = inv.name.strip()
        chosen_names.append(name)
        if name not in TOOL_REGISTRY:
            t0syn = datetime.now(UTC)
            synthetic_tool_calls.append(
                ToolCall(
                    tool_call_id=str(uuid4()),
                    iteration=iteration_next,
                    tool_name=name,
                    args=dict(inv.args),
                    result=None,
                    started_at=t0syn,
                    completed_at=datetime.now(UTC),
                    duration_ms=0,
                    status="error",
                    error=f"Unregistered tool name: {name}",
                ).model_dump(mode="json"),
            )
            continue
        plan_queue.append({"tool_name": name, "args": dict(inv.args)})

    if not parsed.chosen_tools and not terminate:
        terminate = True

    if not plan_queue and not terminate:
        terminate = True

    decision = PlannerDecision(
        iteration=iteration_next,
        chosen_tools=chosen_names,
        rationale=parsed.rationale or "",
        terminate=terminate,
        created_at=datetime.now(UTC),
    )
    elapsed_ms = int((perf_counter() - t0) * 1000)

    out: dict[str, Any] = {
        "plan": plan_queue,
        "planner_decisions": [decision.model_dump(mode="json")],
        "iteration_count": 1,
        "tokens_used": tokens,
        "elapsed_ms": elapsed_ms,
    }
    if synthetic_tool_calls:
        out["tool_calls"] = synthetic_tool_calls
    return out
