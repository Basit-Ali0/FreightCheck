"""Confidence calibration suite (Evaluation Spec §2.2)."""

from __future__ import annotations

from typing import Any

from eval.datasets import TaggedScenario
from eval.extraction import run_extract_all_for_tagged
from eval.helpers import truth_to_extracted_shape, utc_now_iso, values_equal
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts


def _ece(pairs: list[tuple[float, bool]]) -> float:
    if not pairs:
        return 0.0
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(10)]
    for conf, ok in pairs:
        b = min(int(conf * 10), 9)
        bins[b].append((conf, ok))
    total = len(pairs)
    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        mean_c = sum(c for c, _ in bucket) / len(bucket)
        acc = sum(1 for _, o in bucket if o) / len(bucket)
        ece += abs(acc - mean_c) * (len(bucket) / total)
    return ece


def _field_pairs(
    truth_doc: dict[str, Any],
    ext_doc: dict[str, Any],
    conf_doc: dict[str, Any],
) -> list[tuple[float, bool]]:
    out: list[tuple[float, bool]] = []
    for k, tv in truth_doc.items():
        if k == "line_items":
            continue
        ev = ext_doc.get(k)
        meta = conf_doc.get(k) or {}
        conf = float(meta.get("confidence", 1.0))
        out.append((conf, values_equal(tv, ev)))
    li_t = truth_doc.get("line_items")
    li_e = ext_doc.get("line_items")
    meta = conf_doc.get("line_items") or {}
    conf = float(meta.get("confidence", 0.85))
    if isinstance(li_t, list) and isinstance(li_e, list):
        if len(li_t) != len(li_e):
            ok = False
        else:
            ok = all(
                isinstance(a, dict) and isinstance(b, dict) and values_equal(a, b)
                for a, b in zip(li_t, li_e, strict=True)
            )
        out.append((conf, ok))
    return out


class ConfidenceCalibrationSuite(EvalSuite):
    name = "confidence_calibration"
    key_metric = "ece"

    def thresholds(self) -> dict[str, float]:
        return {
            "ece": 0.10,
            "accuracy_at_high_confidence": 0.90,
            "accuracy_at_low_confidence": 0.80,
            "high_confidence_rate": 0.70,
        }

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        all_pairs: list[tuple[float, bool]] = []
        high_pairs: list[tuple[float, bool]] = []
        low_pairs: list[tuple[float, bool]] = []
        consistent_high_num = 0
        consistent_field_num = 0

        for tagged in dataset:
            truth_shape = truth_to_extracted_shape(tagged.scenario.truth)
            try:
                pack = await run_extract_all_for_tagged(tagged, ctx=ctx, snapshot_suite="")
            except Exception as exc:
                per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"error": str(exc)}))  # noqa: E501
                continue
            ext_out = pack["extract"]
            if ext_out.get("error"):
                per.append(ScenarioResult(scenario_id=tagged.scenario_id, details={"error": ext_out["error"]}))  # noqa: E501
                continue
            extracted = ext_out.get("extracted_fields", {})
            conf = ext_out.get("extraction_confidence", {})
            pairs: list[tuple[float, bool]] = []
            for doc in ("bol", "invoice", "packing_list"):
                pairs.extend(
                    _field_pairs(
                        truth_shape[doc],
                        extracted.get(doc, {}),
                        conf.get(doc, {}),
                    ),
                )
            all_pairs.extend(pairs)
            for c, o in pairs:
                if c >= 0.9:  # noqa: PLR2004
                    high_pairs.append((c, o))
                if c < 0.7:  # noqa: PLR2004
                    low_pairs.append((c, o))
            if tagged.scenario.scenario_kind == "consistent":
                for c, _ in pairs:
                    consistent_field_num += 1
                    if c >= 0.9:  # noqa: PLR2004
                        consistent_high_num += 1
            per.append(ScenarioResult(scenario_id=tagged.scenario_id))

        ece = _ece(all_pairs)
        acc_high = (
            sum(1 for _, o in high_pairs if o) / len(high_pairs) if high_pairs else 1.0
        )
        acc_low = sum(1 for _, o in low_pairs if o) / len(low_pairs) if low_pairs else 0.0
        high_rate = (
            consistent_high_num / consistent_field_num if consistent_field_num else 0.0
        )
        metrics = {
            "ece": ece,
            "accuracy_at_high_confidence": acc_high,
            "accuracy_at_low_confidence": acc_low,
            "high_confidence_rate": high_rate,
        }
        thr = self.thresholds()
        passed = (
            metrics["ece"] <= thr["ece"]
            and metrics["accuracy_at_high_confidence"] >= thr["accuracy_at_high_confidence"]
            and metrics["accuracy_at_low_confidence"] <= thr["accuracy_at_low_confidence"]
            and metrics["high_confidence_rate"] >= thr["high_confidence_rate"]
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
