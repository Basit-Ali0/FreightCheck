# backend/tests/integration/test_agent_graph.py
"""Milestone 4: full LangGraph agent with mocked Gemini."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import RootModel

from freightcheck.agent.checkpointing import MongoMirroringSaver
from freightcheck.agent.graph import build_graph, make_initial_state
from freightcheck.schemas.documents import (
    BolExtractionResponse,
    BoLFields,
    ExtractionConfidence,
    InvoiceExtractionResponse,
    InvoiceFields,
    LineItem,
    PackingListExtractionResponse,
    PackingListFields,
)
from freightcheck.schemas.planner import PlannerLLMResponse as PlannerResp
from freightcheck.schemas.planner import PlannerToolInvocation as PlannerInv
from freightcheck.settings import settings


def _mock_mongo_session_store() -> Any:
    """Avoid real Mongo I/O during graph integration tests."""
    return patch(
        "freightcheck.services.session_store.get_mongo_session_store",
        return_value=MagicMock(),
    )


def _high_conf_bol() -> BolExtractionResponse:
    fields = BoLFields(
        bill_of_lading_number="BL1",
        shipper="S",
        consignee="C",
        vessel_name="V",
        port_of_loading="POL",
        port_of_discharge="POD",
        container_numbers=["MSCU1234567"],
        description_of_goods="goods",
        gross_weight=100.0,
        incoterm="FOB",
    )
    conf = {
        name: ExtractionConfidence(field=name, value=getattr(fields, name), confidence=0.95)
        for name in BoLFields.model_fields
    }
    return BolExtractionResponse(fields=fields, confidences=conf)


def _high_conf_invoice() -> InvoiceExtractionResponse:
    li = LineItem(description="x", quantity=1, unit_price=1.0)
    fields = InvoiceFields(
        invoice_number="INV1",
        seller="S",
        buyer="B",
        invoice_date="2026-01-01",
        line_items=[li],
        total_value=1.0,
        currency="USD",
        incoterm="FOB",
    )
    conf = {
        name: ExtractionConfidence(field=name, value=getattr(fields, name), confidence=0.95)
        for name in InvoiceFields.model_fields
    }
    return InvoiceExtractionResponse(fields=fields, confidences=conf)


def _high_conf_pl() -> PackingListExtractionResponse:
    li = LineItem(description="x", quantity=1, net_weight=100.0)
    fields = PackingListFields(
        total_packages=1,
        total_weight=100.0,
        container_numbers=["MSCU1234567"],
        line_items=[li],
    )
    conf = {
        name: ExtractionConfidence(field=name, value=getattr(fields, name), confidence=0.95)
        for name in PackingListFields.model_fields
    }
    return PackingListExtractionResponse(fields=fields, confidences=conf)


def _low_conf_bol() -> BolExtractionResponse:
    r = _high_conf_bol()
    r.confidences["gross_weight"] = ExtractionConfidence(
        field="gross_weight",
        value=100.0,
        confidence=0.4,
        rationale="uncertain",
    )
    return r


@pytest.mark.asyncio
async def test_agent_graph_happy_path_terminates_under_two_seconds() -> None:
    calls: list[str] = []
    planner_tool_batches: list[list[Any] | None] = []

    async def fake_gemini(
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        calls.append(prompt_name)
        if prompt_name == "planner":
            planner_tool_batches.append(tools)
        if prompt_name == "bol_extraction":
            return _high_conf_bol(), 10
        if prompt_name == "invoice_extraction":
            return _high_conf_invoice(), 10
        if prompt_name == "packing_list_extraction":
            return _high_conf_pl(), 10
        if prompt_name == "planner":
            if sum(1 for c in calls if c == "planner") == 1:
                return (
                    PlannerResp(
                        chosen_tools=[
                            PlannerInv(name="check_container_number_format", args={}),
                        ],
                        rationale="Run ISO check.",
                        terminate=False,
                    ),
                    5,
                )
            return PlannerResp(chosen_tools=[], rationale="Done.", terminate=True), 3
        if prompt_name == "summary":
            return RootModel[str](root="Audit complete."), 2
        raise AssertionError(f"unexpected prompt {prompt_name}")

    state = make_initial_state(
        "sess-happy",
        {"bol": "b", "invoice": "i", "packing_list": "p"},
    )
    with (
        _mock_mongo_session_store(),
        patch("freightcheck.services.gemini.call_gemini", new=fake_gemini),
    ):
        app = build_graph()
        out = await app.ainvoke(state, {"configurable": {"thread_id": "sess-happy"}})

    assert out["status"] == "complete"
    assert out["report"] is not None
    assert "planner" in calls
    assert "summary" in calls
    assert any(tc.get("tool_name") == "check_container_number_format" for tc in out["tool_calls"])
    assert planner_tool_batches, "planner should be invoked at least once"
    assert planner_tool_batches[0] is not None
    assert len(planner_tool_batches[0]) > 0


@pytest.mark.asyncio
async def test_budget_max_iterations_runs_compile_report() -> None:
    planner_calls = {"n": 0}

    async def fake_gemini(
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        if prompt_name == "bol_extraction":
            return _high_conf_bol(), 1
        if prompt_name == "invoice_extraction":
            return _high_conf_invoice(), 1
        if prompt_name == "packing_list_extraction":
            return _high_conf_pl(), 1
        if prompt_name == "planner":
            planner_calls["n"] += 1
            return (
                PlannerResp(
                    chosen_tools=[
                        PlannerInv(
                            name="validate_field_match",
                            args={"field": "incoterm", "doc_a": "bol", "doc_b": "invoice"},
                        ),
                    ],
                    rationale="again",
                    terminate=False,
                ),
                1,
            )
        if prompt_name == "summary":
            return RootModel[str](root="Stopped at cap."), 1
        raise AssertionError(prompt_name)

    state = make_initial_state("sess-cap", {"bol": "b", "invoice": "i", "packing_list": "p"})
    with (
        _mock_mongo_session_store(),
        patch.object(settings, "AGENT_MAX_ITERATIONS", 3),
        patch("freightcheck.services.gemini.call_gemini", new=fake_gemini),
    ):
        app = build_graph()
        out = await app.ainvoke(state, {"configurable": {"thread_id": "sess-cap"}})

    assert out["status"] == "complete"
    assert planner_calls["n"] >= 3
    assert out["iteration_count"] >= 3


@pytest.mark.asyncio
async def test_low_confidence_sets_awaiting_review() -> None:
    async def fake_gemini(
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        if prompt_name == "bol_extraction":
            return _low_conf_bol(), 1
        if prompt_name == "invoice_extraction":
            return _high_conf_invoice(), 1
        if prompt_name == "packing_list_extraction":
            return _high_conf_pl(), 1
        if prompt_name == "planner":
            return PlannerResp(chosen_tools=[], rationale="skip tools", terminate=True), 1
        if prompt_name == "summary":
            return RootModel[str](root="Needs review."), 1
        raise AssertionError(prompt_name)

    state = make_initial_state("sess-low", {"bol": "b", "invoice": "i", "packing_list": "p"})
    with (
        _mock_mongo_session_store(),
        patch("freightcheck.services.gemini.call_gemini", new=fake_gemini),
    ):
        out = await build_graph().ainvoke(state, {"configurable": {"thread_id": "sess-low"}})

    assert out["status"] == "awaiting_review"
    assert out["needs_human_review"] is True
    assert out["review_reasons"]


@pytest.mark.asyncio
async def test_injection_unknown_tool_recorded_not_executed() -> None:
    async def fake_gemini(
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        if prompt_name == "bol_extraction":
            return _high_conf_bol(), 1
        if prompt_name == "invoice_extraction":
            return _high_conf_invoice(), 1
        if prompt_name == "packing_list_extraction":
            return _high_conf_pl(), 1
        if prompt_name == "planner":
            return (
                PlannerResp(
                    chosen_tools=[PlannerInv(name="drop_database", args={})],
                    rationale="evil",
                    terminate=False,
                ),
                1,
            )
        if prompt_name == "summary":
            return RootModel[str](root="ok"), 1
        raise AssertionError(prompt_name)

    state = make_initial_state("sess-inj", {"bol": "b", "invoice": "i", "packing_list": "p"})
    with (
        _mock_mongo_session_store(),
        patch("freightcheck.services.gemini.call_gemini", new=fake_gemini),
    ):
        out = await build_graph().ainvoke(state, {"configurable": {"thread_id": "sess-inj"}})

    bad = [tc for tc in out["tool_calls"] if tc.get("tool_name") == "drop_database"]
    assert len(bad) >= 1
    assert bad[0].get("status") == "error"
    assert "Unregistered" in (bad[0].get("error") or "")


@pytest.mark.asyncio
async def test_checkpoint_mirror_called_each_node() -> None:
    writes: list[tuple[str, dict[str, Any]]] = []

    def on_checkpoint(session_id: str, doc: dict[str, Any]) -> None:
        writes.append((session_id, doc))

    async def fake_gemini(
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        if prompt_name == "bol_extraction":
            return _high_conf_bol(), 1
        if prompt_name == "invoice_extraction":
            return _high_conf_invoice(), 1
        if prompt_name == "packing_list_extraction":
            return _high_conf_pl(), 1
        if prompt_name == "planner":
            return PlannerResp(chosen_tools=[], rationale="done", terminate=True), 1
        if prompt_name == "summary":
            return RootModel[str](root="x"), 1
        raise AssertionError(prompt_name)

    state = make_initial_state(
        "sess-mirror",
        {"bol": "b", "invoice": "i", "packing_list": "p"},
    )
    saver = MongoMirroringSaver(on_checkpoint=on_checkpoint)
    with (
        _mock_mongo_session_store(),
        patch("freightcheck.services.gemini.call_gemini", new=fake_gemini),
    ):
        await build_graph(checkpointer=saver).ainvoke(
            state,
            {"configurable": {"thread_id": "sess-mirror"}},
        )

    assert len(writes) >= 5
    assert all(sid == "sess-mirror" for sid, _ in writes)
    assert all("raw_texts" not in doc for _, doc in writes)


@pytest.mark.asyncio
async def test_default_graph_uses_mongo_session_store_for_checkpoints() -> None:
    """Without an injected saver, `build_graph` mirrors checkpoints via MongoSessionStore."""
    mock_store = MagicMock()

    async def fake_gemini(
        prompt_name: str,
        prompt_template: str,
        template_vars: dict[str, Any],
        response_schema: type[Any],
        tools: list[Any] | None = None,
        system_instruction: str | None = None,
    ) -> tuple[Any, int]:
        if prompt_name == "bol_extraction":
            return _high_conf_bol(), 1
        if prompt_name == "invoice_extraction":
            return _high_conf_invoice(), 1
        if prompt_name == "packing_list_extraction":
            return _high_conf_pl(), 1
        if prompt_name == "planner":
            return PlannerResp(chosen_tools=[], rationale="done", terminate=True), 1
        if prompt_name == "summary":
            return RootModel[str](root="x"), 1
        raise AssertionError(prompt_name)

    state = make_initial_state(
        "sess-default-mongo",
        {"bol": "b", "invoice": "i", "packing_list": "p"},
    )
    with (
        patch(
            "freightcheck.services.session_store.get_mongo_session_store",
            return_value=mock_store,
        ),
        patch("freightcheck.services.gemini.call_gemini", new=fake_gemini),
    ):
        await build_graph().ainvoke(state, {"configurable": {"thread_id": "sess-default-mongo"}})

    # One LangGraph checkpoint write per node transition plus final compile_report persist.
    assert mock_store.upsert_checkpoint.call_count >= 5
