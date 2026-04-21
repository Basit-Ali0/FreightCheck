"""Latency suite (Evaluation Spec §2.7)."""

from __future__ import annotations

from eval.datasets import TaggedScenario
from eval.extraction import raw_texts_from_tagged
from eval.graph_runner import run_agent_session
from eval.helpers import percentile, utc_now_iso
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts


class LatencySuite(EvalSuite):
    name = "latency"
    key_metric = "p95_total_ms"

    def thresholds(self) -> dict[str, float]:
        return {
            "p50_total_ms": 20_000.0,
            "p95_total_ms": 30_000.0,
            "max_phase_share": 0.60,
        }

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:  # noqa: ARG002
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        totals: list[float] = []
        extract_ms: list[float] = []
        planner_ms: list[float] = []
        tool_ms: list[float] = []
        compile_ms: list[float] = []

        for tagged in dataset:
            try:
                raw_texts = await raw_texts_from_tagged(tagged)
                final, phase = await run_agent_session(tagged.scenario_id, raw_texts)
            except Exception as exc:
                per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)}))  # noqa: E501
                continue
            totals.append(float(final.get("elapsed_ms", 0)))
            extract_ms.append(phase.get("extract_all", 0.0))
            planner_ms.append(phase.get("plan_validations", 0.0))
            tool_ms.append(phase.get("execute_tool", 0.0))
            compile_ms.append(phase.get("compile_report", 0.0))
            per.append(ScenarioResult(scenario_id=tagged.scenario_id))

        p50_total = percentile(totals, 0.5)
        p50_ext = percentile(extract_ms, 0.5)
        p50_plan = percentile(planner_ms, 0.5)
        p50_tool = percentile(tool_ms, 0.5)
        p50_comp = percentile(compile_ms, 0.5)
        shares = [
            p50_ext / p50_total if p50_total else 0.0,
            p50_plan / p50_total if p50_total else 0.0,
            p50_tool / p50_total if p50_total else 0.0,
            p50_comp / p50_total if p50_total else 0.0,
        ]
        metrics = {
            "p50_total_ms": p50_total,
            "p95_total_ms": percentile(totals, 0.95),
            "p50_extraction_ms": p50_ext,
            "p50_planner_ms": p50_plan,
            "p50_tool_ms": p50_tool,
            "p50_compile_ms": p50_comp,
            "max_phase_share": max(shares) if shares else 0.0,
        }
        thr = self.thresholds()
        passed = (
            metrics["p50_total_ms"] <= thr["p50_total_ms"]
            and metrics["p95_total_ms"] <= thr["p95_total_ms"]
            and metrics["max_phase_share"] <= thr["max_phase_share"]
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
