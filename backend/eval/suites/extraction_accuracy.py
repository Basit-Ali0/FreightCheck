"""Extraction accuracy suite (Evaluation Spec §2.1)."""

from __future__ import annotations

from typing import Any

from eval.datasets import TaggedScenario
from eval.extraction import run_extract_all_for_tagged
from eval.helpers import truth_to_extracted_shape, utc_now_iso, values_equal
from eval.suites.base import EvalContext, EvalSuite, ScenarioResult, SuiteResult
from freightcheck.agent import prompts


def _count_doc(truth_doc: dict[str, Any], ext_doc: Any) -> tuple[int, int, bool]:
    """Return (correct, total, strict_all_correct)."""
    if not isinstance(ext_doc, dict):
        return 0, 1, False
    correct = 0
    total = 0
    strict = True
    for k, tv in truth_doc.items():
        if k == "line_items" and isinstance(tv, list):
            ev = ext_doc.get("line_items")
            if not isinstance(ev, list):
                total += 1
                strict = False
                continue
            for i, tli in enumerate(tv):
                if not isinstance(tli, dict):
                    continue
                if i >= len(ev) or not isinstance(ev[i], dict):
                    total += len(tli)
                    strict = False
                    continue
                eli = ev[i]
                for lk, lv in tli.items():
                    total += 1
                    if values_equal(lv, eli.get(lk)):
                        correct += 1
                    else:
                        strict = False
            continue
        total += 1
        if values_equal(tv, ext_doc.get(k)):
            correct += 1
        else:
            strict = False
    return correct, total, strict


def _invoice_line_item_accuracy(truth: dict[str, Any], ext: dict[str, Any]) -> tuple[int, int]:
    inv_t = truth.get("invoice", {}).get("line_items", [])
    inv_e = ext.get("invoice", {}).get("line_items", [])
    if not isinstance(inv_t, list) or not isinstance(inv_e, list):
        return 0, 1
    ok = 0
    for i, tli in enumerate(inv_t):
        if not isinstance(tli, dict):
            continue
        if i >= len(inv_e) or not isinstance(inv_e[i], dict):
            continue
        eli = inv_e[i]
        if (
            values_equal(tli.get("description"), eli.get("description"))
            and values_equal(tli.get("quantity"), eli.get("quantity"))
            and values_equal(tli.get("unit_price"), eli.get("unit_price"))
        ):
            ok += 1
    return ok, max(len(inv_t), 1)


class ExtractionAccuracySuite(EvalSuite):
    name = "extraction_accuracy"
    key_metric = "field_accuracy"

    def thresholds(self) -> dict[str, float]:
        return {
            "field_accuracy": 0.95,
            "bol_accuracy": 0.92,
            "invoice_accuracy": 0.92,
            "packing_list_accuracy": 0.92,
            "strict_document_accuracy": 0.75,
            "line_item_accuracy": 0.90,
        }

    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:
        started = utc_now_iso()
        per: list[ScenarioResult] = []
        bol_c, bol_t = 0, 0
        inv_c, inv_t = 0, 0
        pl_c, pl_t = 0, 0
        strict_scenarios_ok = 0
        li_ok, li_n = 0, 0
        field_c, field_t = 0, 0

        for tagged in dataset:
            truth_shape = truth_to_extracted_shape(tagged.scenario.truth)
            try:
                pack = await run_extract_all_for_tagged(
                    tagged,
                    ctx=ctx,
                    snapshot_suite="extraction_accuracy" if ctx.save_snapshots else "",
                )
            except Exception as exc:
                per.append(
                    ScenarioResult(
                        scenario_id=tagged.scenario_id,
                        passed=False,
                        details={"error": str(exc)},
                    ),
                )
                continue
            ext_out = pack["extract"]
            if ext_out.get("error"):
                per.append(
                    ScenarioResult(
                        scenario_id=tagged.scenario_id,
                        passed=False,
                        details={"error": ext_out["error"]},
                    ),
                )
                continue
            extracted = ext_out.get("extracted_fields", {})
            cb, tb, sb = _count_doc(truth_shape["bol"], extracted.get("bol"))
            ci, ti, si = _count_doc(truth_shape["invoice"], extracted.get("invoice"))
            cp, tp, sp = _count_doc(truth_shape["packing_list"], extracted.get("packing_list"))
            bol_c += cb
            bol_t += tb
            inv_c += ci
            inv_t += ti
            pl_c += cp
            pl_t += tp
            field_c += cb + ci + cp
            field_t += tb + ti + tp
            if sb and si and sp:
                strict_scenarios_ok += 1
            lok, ln = _invoice_line_item_accuracy(truth_shape, extracted)
            li_ok += lok
            li_n += ln
            per.append(ScenarioResult(scenario_id=tagged.scenario_id, passed=True, details={}))

        n_sc = max(len(dataset), 1)
        metrics = {
            "field_accuracy": field_c / field_t if field_t else 0.0,
            "bol_accuracy": bol_c / bol_t if bol_t else 0.0,
            "invoice_accuracy": inv_c / inv_t if inv_t else 0.0,
            "packing_list_accuracy": pl_c / pl_t if pl_t else 0.0,
            "strict_document_accuracy": strict_scenarios_ok / n_sc,
            "line_item_accuracy": li_ok / li_n if li_n else 0.0,
        }
        thr = self.thresholds()
        passed = all(metrics[k] >= thr[k] for k in thr)
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
