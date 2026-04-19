# backend/src/freightcheck/agent/graph.py
"""LangGraph definition (Flow Spec §1)."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from freightcheck.agent.checkpointing import MongoMirroringSaver
from freightcheck.agent.edges import route_from_reflect
from freightcheck.agent.nodes.compile_report import compile_report
from freightcheck.agent.nodes.execute_tool import execute_tool
from freightcheck.agent.nodes.extract_all import extract_all
from freightcheck.agent.nodes.plan_validations import plan_validations
from freightcheck.agent.nodes.reflect import reflect
from freightcheck.agent.state import AgentState
from freightcheck.services import session_store


def _checkpoint_mongo_write(thread_id: str, doc: dict[str, Any]) -> None:
    """Mirror checkpoints to the shared Mongo-backed session store."""
    session_store.get_mongo_session_store().upsert_checkpoint(thread_id, doc)


def make_initial_state(session_id: str, raw_texts: dict[str, str]) -> AgentState:
    """Build initial `AgentState` for `graph.ainvoke`."""
    return AgentState(
        session_id=session_id,
        raw_texts=raw_texts,
        extracted_fields={},
        extraction_confidence={},
        plan=[],
        tool_calls=[],
        planner_decisions=[],
        iteration_count=0,
        validations=[],
        exceptions=[],
        report=None,
        needs_human_review=False,
        review_reasons=[],
        tokens_used=0,
        elapsed_ms=0,
        error=None,
        status="processing",
    )


def build_graph(*, checkpointer: Any | None = None) -> CompiledStateGraph[AgentState]:
    """Compile the FreightCheck audit graph."""
    if checkpointer is not None:
        saver = checkpointer
    else:
        saver = MongoMirroringSaver(
            on_checkpoint=_checkpoint_mongo_write,
        )
    g: StateGraph[AgentState] = StateGraph(AgentState)
    g.add_node("extract_all", extract_all)
    g.add_node("plan_validations", plan_validations)
    g.add_node("execute_tool", execute_tool)
    g.add_node("reflect", reflect)
    g.add_node("compile_report", compile_report)

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
    return g.compile(checkpointer=saver)
