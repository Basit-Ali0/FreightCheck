"""Grounding suite (Evaluation Spec §2.3)."""

from __future__ import annotations

from eval.datasets import TaggedScenario
from eval.extraction import run_extract_all_for_tagged
from eval.helpers import extraction_is_grounded, iter_extracted_leaf_paths, utc_now_iso
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts


class GroundingSuite(EvalSuite):
    name = "grounding"
    key_metric = "grounding_rate"

    def thresholds(self) -> dict[str, float]:
        return {
            "grounding_rate": 0.95,
            "null_on_missing_rate": 0.85,
            "hallucination_rate": 0.05,
        }

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        grounded = 0
        checked = 0
        hallucinations = 0
        missing_ok = 0
        missing_total = 0

        for tagged in dataset:
            raw_texts: dict[str, str] = {}
            try:
                pack = await run_extract_all_for_tagged(
                    tagged,
                    ctx=ctx,
                    snapshot_suite="grounding" if ctx.save_snapshots else "",
                )
                raw_texts = pack["raw_texts"]
            except Exception as exc:
                per.append(
                    ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)})
                )  # noqa: E501
                continue
            ext_out = pack["extract"]
            if ext_out.get("error"):
                per.append(
                    ScenarioResult(
                        scenario_id=tagged.scenario_id, details={"error": ext_out["error"]}
                    )
                )  # noqa: E501
                continue
            extracted = ext_out.get("extracted_fields", {})
            for doc, blob in extracted.items():
                raw = raw_texts.get(doc, "")
                for path, val in iter_extracted_leaf_paths(doc, blob):
                    if val is None:
                        continue
                    checked += 1
                    if extraction_is_grounded(doc, path, val, raw):
                        grounded += 1
                    else:
                        hallucinations += 1
            if tagged.scenario.scenario_kind == "missing_field":
                missing_total += 1
                inv = extracted.get("invoice", {})
                meta = (ext_out.get("extraction_confidence", {}).get("invoice", {}) or {}).get(
                    "incoterm",
                    {},
                )
                conf = float(meta.get("confidence", 1.0))
                if inv.get("incoterm") in (None, "", "null") and conf < 0.7:  # noqa: PLR2004
                    missing_ok += 1
            per.append(ScenarioResult(scenario_id=tagged.scenario_id))

        metrics = {
            "grounding_rate": grounded / checked if checked else 1.0,
            "null_on_missing_rate": missing_ok / missing_total if missing_total else 1.0,
            "hallucination_rate": hallucinations / checked if checked else 0.0,
        }
        thr = self.thresholds()
        passed = (
            metrics["grounding_rate"] >= thr["grounding_rate"]
            and metrics["null_on_missing_rate"] >= thr["null_on_missing_rate"]
            and metrics["hallucination_rate"] <= thr["hallucination_rate"]
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
