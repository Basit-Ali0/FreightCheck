"""Eval report writer layout."""

from __future__ import annotations

import json
from pathlib import Path

from eval.reporting import write_suite_reports, write_summary
from eval.suites.base import ScenarioResult, SuiteResult


def test_write_summary_and_suite_files(tmp_path: Path) -> None:
    sr = SuiteResult(
        suite="extraction_accuracy",
        metrics={"field_accuracy": 0.99},
        thresholds={"field_accuracy": 0.95},
        per_scenario=[ScenarioResult(scenario_id="extraction_accuracy_0000")],
        passed=True,
        prompt_versions={"planner": "v1"},
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:01:00Z",
        key_metric="field_accuracy",
        key_threshold=0.95,
        key_observed=0.99,
    )
    write_suite_reports(tmp_path, sr)
    write_summary(
        tmp_path,
        git_sha="abc",
        prompt_versions={"planner": "v1"},
        suite_results=[sr],
        baseline_dir=None,
    )
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "summary.md").is_file()
    assert (tmp_path / "extraction_accuracy.json").is_file()
    body = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert body["overall_passed"] is True
    assert "extraction_accuracy" in body["suites"]
