"""Cost / token suite (Evaluation Spec §2.8)."""

from __future__ import annotations

from eval.datasets import TaggedScenario
from eval.extraction import raw_texts_from_tagged
from eval.graph_runner import run_agent_session
from eval.helpers import percentile, utc_now_iso
from eval.pricing import estimate_cost_usd
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts
from freightcheck.settings import settings


class CostSuite(EvalSuite):
    name = "cost"
    key_metric = "p95_tokens_per_session"

    def thresholds(self) -> dict[str, float]:
        return {
            "p50_tokens_per_session": 25_000.0,
            "p95_tokens_per_session": 45_000.0,
            "budget_exhaustion_rate": 0.02,
        }

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:  # noqa: ARG002
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        tokens: list[float] = []
        exhausted = 0

        for tagged in dataset:
            try:
                raw_texts = await raw_texts_from_tagged(tagged)
                final, _ = await run_agent_session(tagged.scenario_id, raw_texts)
            except Exception as exc:
                per.append(
                    ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)})
                )  # noqa: E501
                continue
            t = float(final.get("tokens_used", 0))
            tokens.append(t)
            if int(final.get("tokens_used", 0)) >= settings.AGENT_TOKEN_BUDGET:
                exhausted += 1
            per.append(ScenarioResult(scenario_id=tagged.scenario_id))

        p50 = percentile(tokens, 0.5)
        p95 = percentile(tokens, 0.95)
        n = max(len(dataset), 1)
        metrics = {
            "p50_tokens_per_session": p50,
            "p95_tokens_per_session": p95,
            "p50_cost_usd_per_session": estimate_cost_usd(int(p50)),
            "budget_exhaustion_rate": exhausted / n,
        }
        thr = self.thresholds()
        passed = (
            metrics["p50_tokens_per_session"] <= thr["p50_tokens_per_session"]
            and metrics["p95_tokens_per_session"] <= thr["p95_tokens_per_session"]
            and metrics["budget_exhaustion_rate"] <= thr["budget_exhaustion_rate"]
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
