"""Trajectory correctness suite (Evaluation Spec §2.6)."""

from __future__ import annotations

from collections import Counter

from eval.datasets import TaggedScenario
from eval.extraction import raw_texts_from_tagged
from eval.graph_runner import classify_termination, run_agent_session
from eval.helpers import percentile, utc_now_iso
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from eval.trajectory_expectations import expected_tool_names
from freightcheck.agent import prompts


class TrajectoryCorrectnessSuite(EvalSuite):
    name = "trajectory_correctness"
    key_metric = "expected_tool_coverage"

    def thresholds(self) -> dict[str, float]:
        return {
            "expected_tool_coverage": 0.85,
            "unexpected_tool_rate": 0.20,
            "median_iterations": 5.0,
            "p95_iterations": 8.0,
            "termination_iteration_cap_rate": 0.10,
        }

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:  # noqa: ARG002
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        coverages: list[float] = []
        unexpected_rates: list[float] = []
        iters: list[float] = []
        term_counter: Counter[str] = Counter()

        for tagged in dataset:
            kind = tagged.scenario.scenario_kind
            expected = expected_tool_names(kind)
            try:
                raw_texts = await raw_texts_from_tagged(tagged)
                final, _ = await run_agent_session(tagged.scenario_id, raw_texts)
            except Exception as exc:
                per.append(
                    ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)})
                )  # noqa: E501
                continue
            calls = final.get("tool_calls") or []
            tools = [str(c.get("tool_name", "")) for c in calls if c.get("tool_name")]
            exp_list = list(expected)
            hit = sum(1 for t in exp_list if t in tools)
            cov = hit / len(exp_list) if exp_list else 1.0
            unexpected = [t for t in tools if t not in expected]
            ur = len(unexpected) / len(tools) if tools else 0.0
            ic = float(final.get("iteration_count", 0))
            coverages.append(cov)
            unexpected_rates.append(ur)
            iters.append(ic)
            term_counter[classify_termination(final)] += 1
            per.append(
                ScenarioResult(scenario_id=tagged.scenario_id, details={"tools": tools[:40]})
            )  # noqa: E501

        n = max(len(dataset), 1)  # noqa: F841
        term_total = sum(term_counter.values()) or 1
        metrics = {
            "expected_tool_coverage": sum(coverages) / len(coverages) if coverages else 0.0,
            "unexpected_tool_rate": sum(unexpected_rates) / len(unexpected_rates)
            if unexpected_rates
            else 0.0,  # noqa: E501
            "median_iterations": percentile(iters, 0.5),
            "p95_iterations": percentile(iters, 0.95),
            "termination_iteration_cap_rate": term_counter["iteration_cap"] / term_total,
        }
        thr = self.thresholds()
        passed = (
            metrics["expected_tool_coverage"] >= thr["expected_tool_coverage"]
            and metrics["unexpected_tool_rate"] <= thr["unexpected_tool_rate"]
            and metrics["median_iterations"] <= thr["median_iterations"]
            and metrics["p95_iterations"] <= thr["p95_iterations"]
            and metrics["termination_iteration_cap_rate"] <= thr["termination_iteration_cap_rate"]
        )
        completed = utc_now_iso()
        return SuiteResult(
            suite=self.name,
            metrics=metrics,
            thresholds=thr,
            per_scenario=per,
            passed=passed,
            prompt_versions=dict(prompts.PROMPT_VERSIONS),
            started_at=started,
            completed_at=completed,
            key_metric=self.key_metric,
            key_threshold=thr[self.key_metric],
            key_observed=metrics[self.key_metric],
        )
