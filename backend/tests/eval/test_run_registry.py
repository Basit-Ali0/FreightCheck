"""CLI suite registry."""

from __future__ import annotations

import sys

import pytest
from eval.run import SUITE_REGISTRY, _parse_args


def test_suite_registry_is_explicit() -> None:
    names = [r[0] for r in SUITE_REGISTRY]
    assert names == [
        "extraction_accuracy",
        "confidence_calibration",
        "grounding",
        "mismatch_detection",
        "false_positive",
        "trajectory_correctness",
        "latency",
        "cost",
        "injection_defence",
    ]


def test_parse_args_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["eval.run", "--suite", "latency", "--limit", "3", "--output", "outdir"],
    )
    ns = _parse_args()
    assert ns.suite == "latency"
    assert ns.limit == 3
    assert ns.output == "outdir"
