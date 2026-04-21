"""Mismatch detection suite (Evaluation Spec §2.4)."""

from __future__ import annotations

from collections import defaultdict

from eval.datasets import TaggedScenario
from eval.extraction import raw_texts_from_tagged
from eval.graph_runner import run_agent_session
from eval.helpers import expected_severity_for_kind, utc_now_iso
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts


class MismatchDetectionSuite(EvalSuite):
    name = "mismatch_detection"
    key_metric = "overall_recall"

    def thresholds(self) -> dict[str, float]:
        base = {"overall_recall": 0.90, "correct_severity_rate": 0.85}
        kinds = [
            "incoterm_conflict",
            "quantity_mismatch",
            "weight_mismatch_outside_tolerance",
            "container_number_mismatch",
            "invalid_container_check_digit",
            "incoterm_port_contradiction",
            "description_semantic_mismatch",
            "duplicate_line_items",
        ]
        for k in kinds:
            base[f"recall_{k}"] = 0.80
        return base

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:  # noqa: ARG002
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        kind_hits: dict[str, int] = defaultdict(int)
        kind_totals: dict[str, int] = defaultdict(int)
        sev_ok = 0
        sev_n = 0
        recalled = 0

        for tagged in dataset:
            kind = tagged.scenario.scenario_kind
            kind_totals[kind] += 1
            try:
                raw_texts = await raw_texts_from_tagged(tagged)
                final, _phase = await run_agent_session(tagged.scenario_id, raw_texts)
            except Exception as exc:
                per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)}))  # noqa: E501
                continue
            report = final.get("report") or {}
            exceptions = list(report.get("exceptions") or [])
            hit = any(
                str(e.get("severity", "")).lower() in ("critical", "warning") for e in exceptions
            )
            if hit:
                recalled += 1
                kind_hits[kind] += 1
            sev_n += 1
            exp = expected_severity_for_kind(kind)
            if any(str(e.get("severity", "")).lower() == exp for e in exceptions):
                sev_ok += 1
            per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"hit": hit}))

        n = max(len(dataset), 1)
        metrics: dict[str, float] = {
            "overall_recall": recalled / n,
            "correct_severity_rate": sev_ok / sev_n if sev_n else 0.0,
        }
        for k, tot in kind_totals.items():
            metrics[f"recall_{k}"] = kind_hits[k] / tot if tot else 0.0

        thr = self.thresholds()
        passed = metrics["overall_recall"] >= thr["overall_recall"] and metrics[
            "correct_severity_rate"
        ] >= thr["correct_severity_rate"] and all(
            metrics.get(f"recall_{k}", 1.0) >= thr[f"recall_{k}"]
            for k in [
                "incoterm_conflict",
                "quantity_mismatch",
                "weight_mismatch_outside_tolerance",
                "container_number_mismatch",
                "invalid_container_check_digit",
                "incoterm_port_contradiction",
                "description_semantic_mismatch",
                "duplicate_line_items",
            ]
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
