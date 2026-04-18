"""Structured planner output from Gemini (LangGraph Flow Spec §2.2)."""

from typing import Any

from pydantic import BaseModel, Field


class PlannerToolInvocation(BaseModel):
    """Single tool call the planner wants queued for `execute_tool`."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class PlannerLLMResponse(BaseModel):
    """JSON schema for the planner Gemini call (`prompt_name=planner`)."""

    chosen_tools: list[PlannerToolInvocation] = Field(default_factory=list)
    rationale: str = ""
    terminate: bool = False
