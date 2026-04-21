"""JSON and Markdown report writers (Evaluation Spec §3.2–3.3)."""  # noqa: RUF002

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.helpers import utc_now_iso
from eval.suites.base import ScenarioResult, SuiteResult


def _suite_title(name: str) -> str:
    return name.replace("_", " ").title()


def write_per_scenario(output_dir: Path, suite: str, results: list[ScenarioResult]) -> None:
    d = output_dir / "per_scenario"
    d.mkdir(parents=True, exist_ok=True)
    for r in results:
        path = d / f"{r.scenario_id}.json"
        existing: dict[str, Any] = {}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
        existing[suite] = r.model_dump()
        path.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")


def write_suite_reports(output_dir: Path, result: SuiteResult) -> None:
    name = result.suite
    (output_dir / f"{name}.json").write_text(
        json.dumps(result.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    lines = [
        f"# {_suite_title(name)}",
        "",
        f"**Status**: {'PASS' if result.passed else 'FAIL'}",
        f"**Key metric** `{result.key_metric}`: observed {result.key_observed:.4f}, threshold {result.key_threshold:.4f}",  # noqa: E501
        "",
        "## Metrics",
        "",
        "| Metric | Value | Threshold |",
        "|---|---:|---:|",
    ]
    for k, v in sorted(result.metrics.items()):
        thr = result.thresholds.get(k)
        t = f"{thr:.4f}" if thr is not None else "—"
        lines.append(f"| `{k}` | {v:.4f} | {t} |")
    lines.append("")
    (output_dir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def _baseline_summary(path: Path) -> dict[str, Any] | None:
    p = path / "summary.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def regressions_section(
    current: dict[str, Any],
    baseline_dir: str | None,
) -> str:
    if not baseline_dir:
        return "## Regressions vs last run\n\n_(Baseline path not configured — set `EVAL_BASELINE_DIR` to a prior `reports/<timestamp>` directory.)_\n"  # noqa: E501
    base = _baseline_summary(Path(baseline_dir))
    if not base:
        return "## Regressions vs last run\n\n_(Baseline summary.json not found.)_\n"
    lines = ["## Regressions vs last run", ""]
    cur_suites = current.get("suites", {})
    old_suites = base.get("suites", {})
    found = False
    for name, row in cur_suites.items():
        if not isinstance(row, dict):
            continue
        obs = row.get("key_observed")
        oold = old_suites.get(name, {})
        if not isinstance(oold, dict):
            continue
        prev = oold.get("key_observed")
        if obs is None or prev is None:
            continue
        delta = float(obs) - float(prev)
        if abs(delta) >= 0.02:  # noqa: PLR2004
            found = True
            lines.append(f"- **{name}**: key metric moved by {delta:+.4f} (was {prev:.4f}, now {obs:.4f})")  # noqa: E501
    if not found:
        lines.append("_(No metric shifted by ≥ 2% vs baseline.)_")
    lines.append("")
    return "\n".join(lines)


def write_summary(
    output_dir: Path,
    *,
    git_sha: str,
    prompt_versions: dict[str, str],
    suite_results: list[SuiteResult],
    baseline_dir: str | None,
) -> None:
    started = suite_results[0].started_at if suite_results else utc_now_iso()
    completed = suite_results[-1].completed_at if suite_results else utc_now_iso()
    suites_payload: dict[str, Any] = {}
    for r in suite_results:
        suites_payload[r.suite] = {
            "passed": r.passed,
            "metrics": r.metrics,
            "thresholds": r.thresholds,
            "key_metric": r.key_metric,
            "key_threshold": r.key_threshold,
            "key_observed": r.key_observed,
        }
    overall = all(r.passed for r in suite_results) if suite_results else True
    summary = {
        "started_at": started,
        "completed_at": completed,
        "git_sha": git_sha,
        "prompt_versions": prompt_versions,
        "suites": suites_payload,
        "overall_passed": overall,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    table = [
        "# FreightCheck Eval",
        "",
        f"**Started**: {started}",
        f"**Completed**: {completed}",
        f"**Overall**: {'PASS' if overall else 'FAIL'}",
        f"**Git SHA**: `{git_sha}`",
        "",
        "**Prompt versions**: "
        + ", ".join(f"{k} {v}" for k, v in sorted(prompt_versions.items())),
        "",
        "## Suite Results",
        "",
        "| Suite | Status | Key metric | Threshold | Observed |",
        "|---|---:|---|---:|---:|",
    ]
    for r in suite_results:
        st = "✓" if r.passed else "✗"
        table.append(
            f"| {_suite_title(r.suite)} | {st} | `{r.key_metric}` | "
            f"{r.key_threshold:.4f} | {r.key_observed:.4f} |",
        )
    table.append("")
    table.append(regressions_section(summary, baseline_dir))
    table.append("## Notable failures")
    table.append("")
    fails = [r for r in suite_results if not r.passed]
    if not fails:
        table.append("_(none)_")
    else:
        for r in fails:
            table.append(f"- **{r.suite}** missed thresholds on: " + ", ".join(sorted(r.thresholds.keys())))  # noqa: E501
    table.append("")
    (output_dir / "summary.md").write_text("\n".join(table), encoding="utf-8")
