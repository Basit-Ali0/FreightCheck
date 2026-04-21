"""LangGraph execution with per-node timing for eval (no public API changes)."""

from __future__ import annotations

from time import perf_counter
from typing import Any
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from freightcheck.agent.edges import route_from_reflect
from freightcheck.agent.graph import make_initial_state
from freightcheck.agent.nodes.compile_report import compile_report
from freightcheck.agent.nodes.execute_tool import execute_tool
from freightcheck.agent.nodes.extract_all import extract_all
from freightcheck.agent.nodes.plan_validations import plan_validations
from freightcheck.agent.nodes.reflect import reflect
from freightcheck.agent.state import AgentState
from freightcheck.settings import settings


def build_timed_graph(phase_ms: dict[str, float]) -> CompiledStateGraph[AgentState]:
    """Same topology as ``build_graph`` but accumulates per-node wall time into ``phase_ms``."""

    async def _time(name: str, fn: Any, state: AgentState) -> dict[str, Any]:
        t0 = perf_counter()
        try:
            return await fn(state)
        finally:
            phase_ms[name] = phase_ms.get(name, 0.0) + (perf_counter() - t0) * 1000

    async def extract_all_w(state: AgentState) -> dict[str, Any]:
        return await _time("extract_all", extract_all, state)

    async def plan_validations_w(state: AgentState) -> dict[str, Any]:
        return await _time("plan_validations", plan_validations, state)

    async def execute_tool_w(state: AgentState) -> dict[str, Any]:
        return await _time("execute_tool", execute_tool, state)

    async def reflect_w(state: AgentState) -> dict[str, Any]:
        return await _time("reflect", reflect, state)

    async def compile_report_w(state: AgentState) -> dict[str, Any]:
        return await _time("compile_report", compile_report, state)

    g: StateGraph = StateGraph(AgentState)
    g.add_node("extract_all", extract_all_w)
    g.add_node("plan_validations", plan_validations_w)
    g.add_node("execute_tool", execute_tool_w)
    g.add_node("reflect", reflect_w)
    g.add_node("compile_report", compile_report_w)

    g.add_edge(START, "extract_all")
    g.add_edge("extract_all", "plan_validations")
    g.add_edge("plan_validations", "execute_tool")
    g.add_edge("execute_tool", "reflect")
    g.add_conditional_edges(
        "reflect",
        route_from_reflect,
        {
            "continue": "plan_validations",
            "terminate": "compile_report",
        },
    )
    g.add_edge("compile_report", END)
    return g.compile(checkpointer=InMemorySaver())


def classify_termination(final: AgentState) -> str:
    if final.get("error"):
        return "error"
    decisions = final.get("planner_decisions") or []
    last = decisions[-1] if decisions else None
    if last and last.get("terminate"):
        return "planner_decision"
    if int(final.get("iteration_count", 0)) >= settings.AGENT_MAX_ITERATIONS:
        return "iteration_cap"
    if int(final.get("tokens_used", 0)) >= settings.AGENT_TOKEN_BUDGET:
        return "token_cap"
    if int(final.get("elapsed_ms", 0)) >= settings.AGENT_TIME_BUDGET_MS:
        return "time_cap"
    return "planner_decision"


async def run_agent_session(
    session_id: str, raw_texts: dict[str, str]
) -> tuple[AgentState, dict[str, float]]:  # noqa: E501
    """Run the full graph with Mongo mirror disabled; return final state and phase timings (ms)."""
    phase_ms: dict[str, float] = {}
    state = make_initial_state(session_id, raw_texts)
    with patch(
        "freightcheck.services.session_store.get_mongo_session_store",
        return_value=MagicMock(),
    ):
        app = build_timed_graph(phase_ms)
        final = await app.ainvoke(state, {"configurable": {"thread_id": session_id}})
    return final, phase_ms
