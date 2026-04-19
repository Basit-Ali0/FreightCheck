# backend/src/freightcheck/agent/nodes/compile_report.py
"""`compile_report` node (LangGraph Flow Spec §2.5)."""

from __future__ import annotations

import copy
import inspect
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal

import structlog
from pydantic import RootModel

from freightcheck.agent import prompts
from freightcheck.agent.dispatcher import dispatch
from freightcheck.agent.state import AgentState
from freightcheck.agent.tools import ToolContext
from freightcheck.schemas.audit import AuditReport, SessionStatus
from freightcheck.services import gemini, session_store
from freightcheck.settings import settings

log = structlog.get_logger()

SummaryText = RootModel[str]

# Data Models §6 tolerances
_WEIGHT_TOLERANCE_KG = 0.5
_MONETARY_TOLERANCE = 0.01
_SEMANTIC_SKIP_PREVIEW_COUNT = 12

# Full Data Models §5 validation catalogue (deterministic first, then semantic).
_BASELINE_SEQUENCE: list[tuple[str, dict[str, Any], Literal["deterministic", "semantic"]]] = [
    (
        "validate_field_match",
        {"field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0},
        "deterministic",
    ),
    (
        "validate_field_match",
        {
            "field": "total_quantity",
            "doc_a": "invoice",
            "doc_b": "packing_list",
            "tolerance": 0.0,
        },
        "deterministic",
    ),
    (
        "validate_field_match",
        {
            "field": "gross_weight",
            "doc_a": "bol",
            "doc_b": "packing_list",
            "tolerance": _WEIGHT_TOLERANCE_KG,
            "peer_field": "total_weight",
        },
        "deterministic",
    ),
    ("check_container_consistency", {}, "deterministic"),
    (
        "validate_field_match",
        {
            "field": "invoice_total_vs_line_items",
            "doc_a": "invoice",
            "doc_b": "invoice",
            "tolerance": _MONETARY_TOLERANCE,
        },
        "deterministic",
    ),
    (
        "validate_field_semantic",
        {"field": "description_of_goods", "doc_a": "bol", "doc_b": "invoice"},
        "semantic",
    ),
    (
        "validate_field_semantic",
        {"field": "shipper_seller", "doc_a": "bol", "doc_b": "invoice"},
        "semantic",
    ),
    (
        "validate_field_semantic",
        {"field": "consignee_buyer", "doc_a": "bol", "doc_b": "invoice"},
        "semantic",
    ),
    (
        "validate_field_semantic",
        {"field": "currency_seller_plausibility", "doc_a": "invoice", "doc_b": "invoice"},
        "semantic",
    ),
    ("check_incoterm_port_plausibility", {}, "deterministic"),
    ("check_container_number_format", {}, "deterministic"),
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
    *,
    semantic_allowed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, list[str]]:
    """Return (new_tool_calls, new_validations, new_exceptions, extra_tokens, skipped_semantic)."""
    iteration = int(state.get("iteration_count", 0))
    new_calls: list[dict[str, Any]] = []
    skipped_semantic: list[str] = []
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
    for tool_name, args, kind in _BASELINE_SEQUENCE:
        if kind == "semantic" and not semantic_allowed:
            label = str(args.get("field", tool_name))
            skipped_semantic.append(label)
            continue
        sig = (tool_name, json.dumps(args, sort_keys=True, default=str))
        if sig in keys:
            continue
        call = await dispatch(tool_name, args, ctx, iteration)
        new_calls.append(call)
        keys.add(sig)
    extra_tokens = ctx.tokens_used
    return new_calls, ctx.validations, ctx.exceptions, extra_tokens, skipped_semantic


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


def _semantic_skip_suffix(skipped: list[str]) -> str:
    if not skipped:
        return ""
    slim = ", ".join(skipped[:_SEMANTIC_SKIP_PREVIEW_COUNT])
    more = (
        ""
        if len(skipped) <= _SEMANTIC_SKIP_PREVIEW_COUNT
        else f" (+{len(skipped) - _SEMANTIC_SKIP_PREVIEW_COUNT} more)"
    )
    return (
        f" Semantic baseline checks were skipped due to low remaining token budget: {slim}{more}."
    )


def _summary_inputs(merged_exceptions: list[dict[str, Any]]) -> tuple[str, str]:
    """Build condensed critical/warning context for the summary prompt."""
    top_crit = [e for e in merged_exceptions if e.get("severity") == "critical"][:3]
    top_warn = [e for e in merged_exceptions if e.get("severity") == "warning"][:3]
    top_critical_exceptions = "; ".join(str(e.get("description", "")) for e in top_crit)
    top_warnings = "; ".join(str(e.get("description", "")) for e in top_warn)
    return top_critical_exceptions, top_warnings


def _summary_mode(state: AgentState) -> tuple[bool, bool]:
    """Return fallback-summary mode and whether semantic baseline work is allowed."""
    tokens_used = int(state.get("tokens_used", 0))
    remaining_tokens = max(0, settings.AGENT_TOKEN_BUDGET - tokens_used)
    semantic_allowed = remaining_tokens >= settings.AGENT_SEMANTIC_BASELINE_MIN_REMAINING_TOKENS
    token_budget_hit = tokens_used >= settings.AGENT_TOKEN_BUDGET
    return bool(state.get("error")) or token_budget_hit, semantic_allowed


def _fallback_summary(
    counts: dict[str, int],
    *,
    needs_review: bool,
    skip_suffix: str,
) -> str:
    """Build the deterministic fallback summary string."""
    summary = prompts.SUMMARY_FALLBACK.format(
        critical_count=counts["critical_count"],
        warning_count=counts["warning_count"],
        info_count=counts["info_count"],
        total_count=counts["total_count"],
        review_note=prompts.REVIEW_NOTE_REVIEW if needs_review else prompts.REVIEW_NOTE_OK,
    )
    return (summary + skip_suffix)[:280]


async def _build_summary(
    *,
    counts: dict[str, int],
    needs_review: bool,
    use_fallback: bool,
    skip_suffix: str,
    top_issues: tuple[str, str],
) -> tuple[str, int]:
    """Return the final report summary and any extra summary-call tokens."""
    if use_fallback:
        return _fallback_summary(
            counts,
            needs_review=needs_review,
            skip_suffix=skip_suffix,
        ), 0

    try:
        top_critical_exceptions, top_warnings = top_issues
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
    except Exception:
        return _fallback_summary(
            counts,
            needs_review=needs_review,
            skip_suffix=skip_suffix,
        ), 0

    return (text_m.root + skip_suffix)[:280], tok


async def compile_report(state: AgentState) -> dict[str, Any]:
    """Baseline sweep, counts, summary, final status."""
    t0 = perf_counter()
    keys = _successful_tool_keys(list(state.get("tool_calls", [])))
    use_fallback, semantic_allowed = _summary_mode(state)
    baseline_result = await _run_baseline(
        state,
        keys,
        semantic_allowed=semantic_allowed,
    )
    baseline_calls, baseline_vals, baseline_exc, baseline_tokens, skipped_semantic = baseline_result
    skip_suffix = _semantic_skip_suffix(skipped_semantic)

    merged_exceptions = list(state.get("exceptions", [])) + baseline_exc
    merged_validations = list(state.get("validations", [])) + baseline_vals

    counts = _count_report(merged_validations, merged_exceptions)

    needs_review = bool(state.get("needs_human_review", False))
    err = state.get("error")
    top_critical_exceptions, top_warnings = _summary_inputs(merged_exceptions)
    summary, summary_tokens = await _build_summary(
        counts=counts,
        needs_review=needs_review,
        use_fallback=use_fallback,
        skip_suffix=skip_suffix,
        top_issues=(top_critical_exceptions, top_warnings),
    )
    extra_tokens = baseline_tokens + summary_tokens

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

    completed_at = datetime.now(UTC).isoformat()
    elapsed_ms = int((perf_counter() - t0) * 1000)
    log.info("agent.compile_report", session_id=state["session_id"], status=status)

    out: dict[str, Any] = {
        "report": report.model_dump(mode="json"),
        "status": status,
        "completed_at": completed_at,
        "elapsed_ms": elapsed_ms,
        "tokens_used": extra_tokens,
        "validations": baseline_vals,
        "exceptions": baseline_exc,
    }
    if baseline_calls:
        out["tool_calls"] = baseline_calls

    try:
        store = session_store.get_mongo_session_store()
        payload = {
            "report": report.model_dump(mode="json"),
            "status": status,
            "completed_at": completed_at,
            "error_message": state.get("error"),
        }
        upsert_async = getattr(store, "upsert_checkpoint_async", None)
        if inspect.iscoroutinefunction(upsert_async):
            await store.upsert_checkpoint_async(
                state["session_id"],
                payload,
            )
        else:
            store.upsert_checkpoint(
                state["session_id"],
                payload,
            )
    except Exception:
        log.exception("agent.compile_report_persist_failed", session_id=state["session_id"])

    return out
