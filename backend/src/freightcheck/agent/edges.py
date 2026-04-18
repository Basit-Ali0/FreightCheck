# backend/src/freightcheck/agent/edges.py
"""Conditional edges for the LangGraph agent (Flow Spec §2.4)."""

from __future__ import annotations

from typing import Literal

from freightcheck.agent.state import AgentState
from freightcheck.settings import settings


def route_from_reflect(state: AgentState) -> Literal["continue", "terminate"]:
    """Route after `reflect`: loop to planner or finish to `compile_report`."""
    if state.get("error"):
        return "terminate"
    decisions = state.get("planner_decisions") or []
    last = decisions[-1] if decisions else None
    if last and last.get("terminate"):
        return "terminate"
    if int(state.get("iteration_count", 0)) >= settings.AGENT_MAX_ITERATIONS:
        return "terminate"
    if int(state.get("tokens_used", 0)) >= settings.AGENT_TOKEN_BUDGET:
        return "terminate"
    if int(state.get("elapsed_ms", 0)) >= settings.AGENT_TIME_BUDGET_MS:
        return "terminate"
    return "continue"
