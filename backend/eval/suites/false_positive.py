"""False positive suite (Evaluation Spec §2.5)."""

from __future__ import annotations

from eval.datasets import TaggedScenario
from eval.extraction import raw_texts_from_tagged
from eval.graph_runner import run_agent_session
from eval.helpers import utc_now_iso
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts


class FalsePositiveSuite(EvalSuite):
    name = "false_positive"
    key_metric = "false_positive_rate"

    def thresholds(self) -> dict[str, float]:
        return {"false_positive_rate": 0.05, "critical_false_positive_rate": 0.01}

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:  # noqa: ARG002
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        fp = 0
        cfp = 0
        n = len(dataset)

        for tagged in dataset:
            if tagged.scenario.scenario_kind not in (
                "consistent",
                "weight_mismatch_within_tolerance",
                "description_semantic_match",
            ):
                continue
            try:
                raw_texts = await raw_texts_from_tagged(tagged)
                final, _ = await run_agent_session(tagged.scenario_id, raw_texts)
            except Exception as exc:
                per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)}))  # noqa: E501
                continue
            report = final.get("report") or {}
            exceptions = list(report.get("exceptions") or [])
            bad = any(str(e.get("severity", "")).lower() in ("critical", "warning") for e in exceptions)  # noqa: E501
            crit = any(str(e.get("severity", "")).lower() == "critical" for e in exceptions)
            if bad:
                fp += 1
            if crit:
                cfp += 1
            per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"fp": bad}))

        denom = max(n, 1)
        metrics = {
            "false_positive_rate": fp / denom,
            "critical_false_positive_rate": cfp / denom,
        }
        thr = self.thresholds()
        passed = metrics["false_positive_rate"] <= thr["false_positive_rate"] and metrics[
            "critical_false_positive_rate"
        ] <= thr["critical_false_positive_rate"]
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
