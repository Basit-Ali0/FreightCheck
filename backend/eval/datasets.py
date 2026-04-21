"""Deterministic eval datasets (Evaluation Spec §1.4)."""

from __future__ import annotations

from dataclasses import dataclass

from eval.scenarios import (
    SCENARIO_BUILDERS,
    consistent,
    container_number_mismatch,
    currency_symbol_ambiguous,
    description_semantic_match,
    description_semantic_mismatch,
    duplicate_line_items,
    duplicate_line_items_mismatch,
    incoterm_conflict,
    incoterm_port_contradiction,
    injection_fake_tag,
    injection_override,
    invalid_container_check_digit,
    low_quality_pdf,
    missing_field,
    quantity_mismatch,
    weight_mismatch_outside_tolerance,
    weight_mismatch_within_tolerance,
)
from eval.synthetic_generator import ShipmentScenario

EXTRACTION_ACCURACY_N = 50
CONFIDENCE_CALIBRATION_N = 100
MISMATCH_DETECTION_N = 80
FALSE_POSITIVE_N = 50
TRAJECTORY_CORRECTNESS_N = 30
INJECTION_DEFENCE_N = 20
GROUNDING_N = 40
LATENCY_COST_N = 30

# Hard-coded suite bases (Evaluation Spec §1.4 determinism)
_SEED_EXTRACTION = 1_000_000
_SEED_CONFIDENCE = 2_000_000
_SEED_MISMATCH = 3_000_000
_SEED_FALSE_POS = 4_000_000
_SEED_TRAJECTORY = 5_000_000
_SEED_INJECTION = 6_000_000
_SEED_GROUNDING = 7_000_000
_SEED_LATENCY = 8_000_000


@dataclass(frozen=True)
class TaggedScenario:
    """A scenario with stable id and PDF generation seed."""

    scenario_id: str
    scenario: ShipmentScenario
    pdf_seed: int


def _tag(suite: str, idx: int, scenario: ShipmentScenario, pdf_seed: int) -> TaggedScenario:
    return TaggedScenario(scenario_id=f"{suite}_{idx:04d}", scenario=scenario, pdf_seed=pdf_seed)


def build_extraction_accuracy_dataset() -> list[TaggedScenario]:
    out: list[TaggedScenario] = []
    for i in range(EXTRACTION_ACCURACY_N):
        pdf_seed = _SEED_EXTRACTION + i * 17
        if i % 10 == 0:
            sc = duplicate_line_items(_SEED_EXTRACTION + i)
        else:
            sc = consistent(_SEED_EXTRACTION + i)
        out.append(_tag("extraction_accuracy", i, sc, pdf_seed))
    return out


def build_confidence_calibration_dataset() -> list[TaggedScenario]:
    out: list[TaggedScenario] = []
    for i in range(CONFIDENCE_CALIBRATION_N):
        pdf_seed = _SEED_CONFIDENCE + i * 19
        if i % 10 < 7:  # noqa: PLR2004
            sc = consistent(_SEED_CONFIDENCE + i)
        else:
            sc = low_quality_pdf(_SEED_CONFIDENCE + i)
        out.append(_tag("confidence_calibration", i, sc, pdf_seed))
    return out


def build_mismatch_detection_dataset() -> list[TaggedScenario]:
    builders = [
        incoterm_conflict,
        quantity_mismatch,
        weight_mismatch_outside_tolerance,
        container_number_mismatch,
        invalid_container_check_digit,
        incoterm_port_contradiction,
        description_semantic_mismatch,
        duplicate_line_items_mismatch,
    ]
    out: list[TaggedScenario] = []
    idx = 0
    for _rep in range(10):
        for b in builders:
            seed = _SEED_MISMATCH + idx * 23
            out.append(_tag("mismatch_detection", idx, b(seed), seed))
            idx += 1
    return out


def build_false_positive_dataset() -> list[TaggedScenario]:
    out: list[TaggedScenario] = []
    cycle = [consistent, weight_mismatch_within_tolerance, description_semantic_match]
    for i in range(FALSE_POSITIVE_N):
        seed = _SEED_FALSE_POS + i * 29
        sc = cycle[i % len(cycle)](seed)
        out.append(_tag("false_positive", i, sc, seed))
    return out


def build_trajectory_dataset() -> list[TaggedScenario]:
    kinds = list(SCENARIO_BUILDERS.keys())
    out: list[TaggedScenario] = []
    for i in range(TRAJECTORY_CORRECTNESS_N):
        seed = _SEED_TRAJECTORY + i * 31
        kind = kinds[i % len(kinds)]
        sc = SCENARIO_BUILDERS[kind](seed)
        out.append(_tag("trajectory_correctness", i, sc, seed))
    return out


def build_injection_defence_dataset() -> list[TaggedScenario]:
    out: list[TaggedScenario] = []
    for i in range(INJECTION_DEFENCE_N):
        seed = _SEED_INJECTION + i * 37
        builder = injection_override if i % 2 == 0 else injection_fake_tag
        out.append(_tag("injection_defence", i, builder(seed), seed))
    return out


def build_grounding_dataset() -> list[TaggedScenario]:
    cycle = [consistent, missing_field, currency_symbol_ambiguous]
    out: list[TaggedScenario] = []
    for i in range(GROUNDING_N):
        seed = _SEED_GROUNDING + i * 41
        sc = cycle[i % len(cycle)](seed)
        out.append(_tag("grounding", i, sc, seed))
    return out


def build_latency_cost_dataset() -> list[TaggedScenario]:
    out: list[TaggedScenario] = []
    for i in range(LATENCY_COST_N):
        seed = _SEED_LATENCY + i * 43
        sc = consistent(seed)
        out.append(_tag("latency_cost", i, sc, seed))
    return out
