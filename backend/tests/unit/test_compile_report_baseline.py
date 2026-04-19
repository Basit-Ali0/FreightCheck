# backend/tests/unit/test_compile_report_baseline.py
"""`compile_report` baseline catalogue coverage."""

from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import RootModel

from freightcheck.agent.state import AgentState
from freightcheck.settings import settings

_compile_report = importlib.import_module("freightcheck.agent.nodes.compile_report")


def _state(**overrides: Any) -> AgentState:
    base: dict[str, Any] = {
        "session_id": "s-baseline",
        "raw_texts": {},
        "extracted_fields": {
            "bol": {
                "incoterm": "FOB",
                "gross_weight": 100.0,
                "container_numbers": ["MSCU1234566"],
                "description_of_goods": "Cotton shirts",
                "shipper": "Acme Ltd",
                "consignee": "Buyer Co",
                "port_of_loading": "Shanghai, China",
                "port_of_discharge": "",
            },
            "invoice": {
                "incoterm": "FOB",
                "currency": "USD",
                "seller": "US Seller Inc",
                "buyer": "Buyer Co",
                "total_value": 100.01,
                "line_items": [
                    {"description": "Cotton shirts", "quantity": 10, "unit_price": 10.0},
                ],
            },
            "packing_list": {
                "total_weight": 100.2,
                "container_numbers": ["MSCU1234566"],
                "line_items": [{"description": "x", "quantity": 10, "net_weight": 1.0}],
            },
        },
        "extraction_confidence": {},
        "plan": [],
        "tool_calls": [],
        "planner_decisions": [],
        "iteration_count": 2,
        "validations": [],
        "exceptions": [],
        "report": None,
        "needs_human_review": False,
        "review_reasons": [],
        "tokens_used": 0,
        "elapsed_ms": 0,
        "error": None,
        "status": "processing",
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_compile_report_baseline_runs_full_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_dispatch(
        tool_name: str,
        args: dict[str, Any],
        ctx: object,
        iteration: int,
    ) -> dict[str, Any]:
        calls.append((tool_name, dict(args)))
        return {
            "tool_call_id": "x",
            "iteration": iteration,
            "tool_name": tool_name,
            "args": args,
            "result": {"ok": True},
            "started_at": "t0",
            "completed_at": "t1",
            "duration_ms": 1,
            "status": "success",
            "error": None,
        }

    async def fake_summary(**_kw: Any) -> tuple[RootModel[str], int]:
        return RootModel[str](root="ok"), 0

    monkeypatch.setattr(_compile_report, "dispatch", fake_dispatch)
    monkeypatch.setattr(_compile_report.gemini, "call_gemini", fake_summary)

    mongo = MagicMock()
    with patch.object(
        _compile_report.session_store,
        "get_mongo_session_store",
        return_value=mongo,
    ):
        await _compile_report.compile_report(_state())

    names = [c[0] for c in calls]
    assert "validate_field_match" in names
    assert names.count("validate_field_match") >= 4  # incoterm, total_qty, weight, invoice total
    assert "check_container_consistency" in names
    assert "check_incoterm_port_plausibility" in names
    assert "check_container_number_format" in names
    assert "validate_field_semantic" in names
    assert mongo.upsert_checkpoint.called


@pytest.mark.asyncio
async def test_compile_report_skips_semantic_when_token_budget_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    semantic_calls = 0

    async def fake_dispatch(
        tool_name: str,
        args: dict[str, Any],
        *_a: object,
        **_k: object,
    ) -> dict[str, Any]:
        nonlocal semantic_calls
        if tool_name == "validate_field_semantic":
            semantic_calls += 1
        return {
            "tool_call_id": "x",
            "iteration": 1,
            "tool_name": tool_name,
            "args": args,
            "result": {},
            "started_at": "t0",
            "completed_at": "t1",
            "duration_ms": 1,
            "status": "success",
            "error": None,
        }

    async def fake_summary(**_kw: Any) -> tuple[RootModel[str], int]:
        return RootModel[str](root="summary"), 0

    monkeypatch.setattr(_compile_report, "dispatch", fake_dispatch)
    monkeypatch.setattr(_compile_report.gemini, "call_gemini", fake_summary)

    st = _state()
    st["tokens_used"] = settings.AGENT_TOKEN_BUDGET - 100  # below semantic reserve

    with patch.object(
        _compile_report.session_store,
        "get_mongo_session_store",
        return_value=MagicMock(),
    ):
        out = await _compile_report.compile_report(st)

    assert semantic_calls == 0
    summary = out["report"]["summary"]
    assert "skipped" in summary.lower() or "Semantic baseline" in summary


@pytest.mark.asyncio
async def test_compile_report_weight_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    """§6: weight absolute tolerance ±0.5 kg."""
    weight_args: dict[str, Any] | None = None

    async def fake_dispatch(
        tool_name: str,
        args: dict[str, Any],
        *_a: object,
        **_k: object,
    ) -> dict[str, Any]:
        nonlocal weight_args
        if tool_name == "validate_field_match" and args.get("field") == "gross_weight":
            weight_args = dict(args)
        return {
            "tool_call_id": "x",
            "iteration": 1,
            "tool_name": tool_name,
            "args": args,
            "result": {},
            "started_at": "t0",
            "completed_at": "t1",
            "duration_ms": 1,
            "status": "success",
            "error": None,
        }

    monkeypatch.setattr(_compile_report, "dispatch", fake_dispatch)
    monkeypatch.setattr(
        _compile_report.gemini,
        "call_gemini",
        AsyncMock(return_value=(RootModel[str](root="x"), 0)),
    )

    with patch.object(
        _compile_report.session_store,
        "get_mongo_session_store",
        return_value=MagicMock(),
    ):
        await _compile_report.compile_report(_state())

    assert weight_args is not None
    assert weight_args.get("tolerance") == pytest.approx(0.5)
    assert weight_args.get("peer_field") == "total_weight"
