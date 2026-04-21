"""CLI entrypoint: ``python -m eval.run`` (Evaluation Spec §3.1)."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from eval.datasets import (
    TaggedScenario,
    build_confidence_calibration_dataset,
    build_extraction_accuracy_dataset,
    build_false_positive_dataset,
    build_grounding_dataset,
    build_injection_defence_dataset,
    build_latency_cost_dataset,
    build_mismatch_detection_dataset,
    build_trajectory_dataset,
)
from eval.helpers import git_sha
from eval.reporting import write_per_scenario, write_suite_reports, write_summary
from eval.suites.base import EvalContext, EvalSuite, SuiteResult
from eval.suites.confidence_calibration import ConfidenceCalibrationSuite
from eval.suites.cost import CostSuite
from eval.suites.extraction_accuracy import ExtractionAccuracySuite
from eval.suites.false_positive import FalsePositiveSuite
from eval.suites.grounding import GroundingSuite
from eval.suites.injection_defence import InjectionDefenceSuite
from eval.suites.latency import LatencySuite
from eval.suites.mismatch_detection import MismatchDetectionSuite
from eval.suites.trajectory_correctness import TrajectoryCorrectnessSuite
from freightcheck.agent import prompts

SNAPSHOT_SUITES = frozenset({"extraction_accuracy", "grounding", "injection_defence"})

SUITE_REGISTRY: list[tuple[str, type[EvalSuite], Callable[[], list[TaggedScenario]]]] = [
    ("extraction_accuracy", ExtractionAccuracySuite, build_extraction_accuracy_dataset),
    ("confidence_calibration", ConfidenceCalibrationSuite, build_confidence_calibration_dataset),
    ("grounding", GroundingSuite, build_grounding_dataset),
    ("mismatch_detection", MismatchDetectionSuite, build_mismatch_detection_dataset),
    ("false_positive", FalsePositiveSuite, build_false_positive_dataset),
    ("trajectory_correctness", TrajectoryCorrectnessSuite, build_trajectory_dataset),
    ("latency", LatencySuite, build_latency_cost_dataset),
    ("cost", CostSuite, build_latency_cost_dataset),
    ("injection_defence", InjectionDefenceSuite, build_injection_defence_dataset),
]


def _default_output_dir() -> Path:
    here = Path(__file__).resolve().parent
    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return here / "reports" / ts


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FreightCheck evaluation harness (M7).")
    p.add_argument("--all", action="store_true", help="Run every registered suite.")
    p.add_argument("--suite", type=str, default=None, help="Run a single suite by name.")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--output", type=str, default=None, help="Report output directory.")
    p.add_argument("--save-snapshots", action="store_true")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap scenarios per suite (development / smoke testing).",
    )
    return p.parse_args()


async def _run_suite(
    name: str,
    suite_cls: type[EvalSuite],
    dataset_fn: Callable[[], list[TaggedScenario]],
    ctx: EvalContext,
    limit: int | None,
) -> SuiteResult:
    data = dataset_fn()
    if limit is not None:
        data = data[:limit]
    snap = ctx.save_snapshots and name in SNAPSHOT_SUITES
    ctx = ctx.model_copy(update={"save_snapshots": snap})
    suite = suite_cls()
    return await suite.run(data, ctx)


def main() -> int:
    args = _parse_args()
    if not args.all and not args.suite:
        print("Specify --all or --suite <name>")  # noqa: T201
        return 2

    out = Path(args.output) if args.output else _default_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    baseline = os.environ.get("EVAL_BASELINE_DIR")

    selected: list[tuple[str, type[EvalSuite], Callable[[], list[TaggedScenario]]]] = []
    if args.suite:
        for row in SUITE_REGISTRY:
            if row[0] == args.suite:
                selected = [row]
                break
        if not selected:
            print(f"Unknown suite {args.suite!r}. Valid: {[r[0] for r in SUITE_REGISTRY]}")  # noqa: T201
            return 2
    else:
        selected = list(SUITE_REGISTRY)

    ctx = EvalContext(
        verbose=args.verbose,
        save_snapshots=args.save_snapshots,
        output_dir=str(out),
    )

    async def _runner() -> list[SuiteResult]:
        results: list[SuiteResult] = []
        for name, cls, fn in selected:
            r = await _run_suite(name, cls, fn, ctx, args.limit)
            results.append(r)
            write_suite_reports(out, r)
            write_per_scenario(out, r.suite, r.per_scenario)
        return results

    suite_results = asyncio.run(_runner())
    write_summary(
        out,
        git_sha=git_sha(),
        prompt_versions=dict(prompts.PROMPT_VERSIONS),
        suite_results=suite_results,
        baseline_dir=baseline,
    )
    overall = all(r.passed for r in suite_results)
    print(f"Wrote reports under {out}")  # noqa: T201
    print(f"overall_passed={overall}")  # noqa: T201
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
