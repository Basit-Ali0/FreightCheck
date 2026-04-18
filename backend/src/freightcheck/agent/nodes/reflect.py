# backend/src/freightcheck/agent/nodes/reflect.py
"""`reflect` node (LangGraph Flow Spec §2.4) — routing only via `edges.route_from_reflect`."""

from __future__ import annotations

from typing import Any

from freightcheck.agent.state import AgentState


async def reflect(_state: AgentState) -> dict[str, Any]:
    """Pure routing step; no state mutation."""
    return {}
