# backend/tests/unit/test_dispatcher.py
"""Dispatcher funnel tests (Flow Spec §5)."""

from __future__ import annotations

import pytest
from langchain_core.tools import StructuredTool

from freightcheck.agent import tools as tools_mod
from freightcheck.agent.dispatcher import dispatch
from freightcheck.agent.tools import TOOL_REGISTRY, ToolContext, _SemanticResponse
from freightcheck.schemas.audit import ValidationStatus


def _ctx() -> ToolContext:
    return ToolContext(session_id="s1")


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_name() -> None:
    out = await dispatch("not_a_real_tool", {}, _ctx(), iteration=1)
    assert out["status"] == "error"
    assert "Unregistered" in (out.get("error") or "")


@pytest.mark.asyncio
async def test_dispatch_args_schema_validation_failure() -> None:
    out = await dispatch(
        "validate_field_match",
        {"field": "incoterm", "doc_a": "bol", "doc_b": "notadoc"},
        _ctx(),
        iteration=2,
    )
    assert out["status"] == "error"
    error = out.get("error") or ""
    assert "ValidationError" in error or "doc" in error.lower()


@pytest.mark.asyncio
async def test_dispatch_sync_tool_success() -> None:
    ctx = _ctx()
    ctx.extracted_fields = {"bol": {"incoterm": "FOB"}, "invoice": {"incoterm": "fob"}}
    out = await dispatch(
        "validate_field_match",
        {"field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0},
        ctx,
        iteration=1,
    )
    assert out["status"] == "success"
    assert out.get("result") is not None


@pytest.mark.asyncio
async def test_dispatch_async_tool_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_gemini(**_kw: object) -> tuple[object, int]:
        return _SemanticResponse(status=ValidationStatus.MATCH, reason="ok"), 5

    monkeypatch.setattr(tools_mod.gemini, "call_gemini", fake_gemini)

    ctx = _ctx()
    ctx.extracted_fields = {"bol": {"shipper": "A"}, "invoice": {"shipper": "A"}}
    out = await dispatch(
        "validate_field_semantic",
        {"field": "shipper", "doc_a": "bol", "doc_b": "invoice"},
        ctx,
        iteration=3,
    )
    assert out["status"] == "success"


@pytest.mark.asyncio
async def test_dispatch_maps_impl_exception_to_failed_tool_call() -> None:
    ctx = _ctx()
    ctx.extracted_fields = {"bol": {"incoterm": "CIF"}, "invoice": {"incoterm": ["x"]}}
    out = await dispatch(
        "validate_field_match",
        {"field": "incoterm", "doc_a": "bol", "doc_b": "invoice"},
        ctx,
        iteration=1,
    )
    assert out["status"] == "error"
    assert "ValueError" in (out.get("error") or "")


def test_tool_registry_entries_are_structured_tools() -> None:
    for name, tool in TOOL_REGISTRY.items():
        assert isinstance(tool, StructuredTool), name
        assert tool.args_schema is not None, name
