# backend/src/freightcheck/agent/nodes/compile_report.py
"""`compile_report` node (LangGraph Flow Spec §2.5)."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import structlog
from pydantic import RootModel

from freightcheck.agent import prompts
from freightcheck.agent.dispatcher import dispatch
from freightcheck.agent.state import AgentState
from freightcheck.agent.tools import ToolContext
from freightcheck.schemas.audit import AuditReport, SessionStatus
from freightcheck.services import gemini
from freightcheck.settings import settings

log = structlog.get_logger()

SummaryText = RootModel[str]

_BASELINE_SEQUENCE: list[tuple[str, dict[str, Any]]] = [
    ("check_container_consistency", {}),
    ("check_incoterm_port_plausibility", {}),
    ("check_container_number_format", {}),
    (
        "validate_field_match",
        {"field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0},
    ),
    (
        "validate_field_match",
        {"field": "gross_weight", "doc_a": "bol", "doc_b": "packing_list", "tolerance": 0.01},
    ),
]


def _successful_tool_keys(tool_calls: list[dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for c in tool_calls:
        if c.get("status") != "success":
            continue
        name = str(c.get("tool_name", ""))
        args = c.get("args") if isinstance(c.get("args"), dict) else {}
        keys.add((name, json.dumps(args, sort_keys=True, default=str)))
    return keys


async def _run_baseline(
    state: AgentState,
    keys: set[tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    """Return (new_tool_calls, new_validations, new_exceptions, extra_tokens)."""
    iteration = int(state.get("iteration_count", 0))
    extra_tokens = 0
    new_calls: list[dict[str, Any]] = []
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
    for tool_name, args in _BASELINE_SEQUENCE:
        sig = (tool_name, json.dumps(args, sort_keys=True, default=str))
        if sig in keys:
            continue
        call = await dispatch(tool_name, args, ctx, iteration)
        new_calls.append(call)
        keys.add(sig)
    extra_tokens = ctx.tokens_used
    return new_calls, ctx.validations, ctx.exceptions, extra_tokens


def _count_report(
    validations: list[dict[str, Any]], exceptions: list[dict[str, Any]]
) -> dict[str, int]:
    passed = sum(1 for v in validations if v.get("status") == "match")
    critical = warning = info = 0
    for e in exceptions:
        sev = e.get("severity")
        if sev == "critical":
            critical += 1
        elif sev == "warning":
            warning += 1
        elif sev == "info":
            info += 1
    return {
        "critical_count": critical,
        "warning_count": warning,
        "info_count": info,
        "passed_count": passed,
        "total_count": len(validations),
    }


async def compile_report(state: AgentState) -> dict[str, Any]:
    """Baseline sweep, counts, summary, final status."""
    t0 = perf_counter()
    keys = _successful_tool_keys(list(state.get("tool_calls", [])))
    baseline_calls, baseline_vals, baseline_exc, baseline_tokens = await _run_baseline(state, keys)

    merged_exceptions = list(state.get("exceptions", [])) + baseline_exc
    merged_validations = list(state.get("validations", [])) + baseline_vals

    counts = _count_report(merged_validations, merged_exceptions)

    needs_review = bool(state.get("needs_human_review", False))
    err = state.get("error")
    token_budget_hit = int(state.get("tokens_used", 0)) >= settings.AGENT_TOKEN_BUDGET
    use_fallback = bool(err) or token_budget_hit

    top_crit = [e for e in merged_exceptions if e.get("severity") == "critical"][:3]
    top_warn = [e for e in merged_exceptions if e.get("severity") == "warning"][:3]
    top_critical_exceptions = "; ".join(str(e.get("description", "")) for e in top_crit)
    top_warnings = "; ".join(str(e.get("description", "")) for e in top_warn)

    summary: str
    extra_tokens = baseline_tokens
    if use_fallback:
        summary = prompts.SUMMARY_FALLBACK.format(
            critical_count=counts["critical_count"],
            warning_count=counts["warning_count"],
            info_count=counts["info_count"],
            total_count=counts["total_count"],
            review_note=prompts.REVIEW_NOTE_REVIEW if needs_review else prompts.REVIEW_NOTE_OK,
        )
    else:
        try:
            text_m, tok = await gemini.call_gemini(
                prompt_name="summary",
                prompt_template=prompts.SUMMARY_PROMPT,
                template_vars={
                    "critical_count": counts["critical_count"],
                    "warning_count": counts["warning_count"],
                    "info_count": counts["info_count"],
                    "passed_count": counts["passed_count"],
                    "needs_human_review": needs_review,
                    "top_critical_exceptions": top_critical_exceptions or "(none)",
                    "top_warnings": top_warnings or "(none)",
                },
                response_schema=SummaryText,
            )
            summary = text_m.root[:280]
            extra_tokens += tok
        except Exception:
            summary = prompts.SUMMARY_FALLBACK.format(
                critical_count=counts["critical_count"],
                warning_count=counts["warning_count"],
                info_count=counts["info_count"],
                total_count=counts["total_count"],
                review_note=prompts.REVIEW_NOTE_REVIEW if needs_review else prompts.REVIEW_NOTE_OK,
            )

    report = AuditReport(
        critical_count=counts["critical_count"],
        warning_count=counts["warning_count"],
        info_count=counts["info_count"],
        passed_count=counts["passed_count"],
        summary=summary[:280],
    )

    if err:
        status: str = SessionStatus.FAILED.value
    elif needs_review:
        status = SessionStatus.AWAITING_REVIEW.value
    else:
        status = SessionStatus.COMPLETE.value

    elapsed_ms = int((perf_counter() - t0) * 1000)
    log.info("agent.compile_report", session_id=state["session_id"], status=status)

    out: dict[str, Any] = {
        "report": report.model_dump(mode="json"),
        "status": status,
        "completed_at": datetime.now(UTC).isoformat(),
        "elapsed_ms": elapsed_ms,
        "tokens_used": extra_tokens,
        "validations": baseline_vals,
        "exceptions": baseline_exc,
    }
    if baseline_calls:
        out["tool_calls"] = baseline_calls
    return out
