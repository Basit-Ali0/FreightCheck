"""Shared eval suite types (Evaluation Spec §2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from eval.datasets import TaggedScenario


class ScenarioResult(BaseModel):
    scenario_id: str
    passed: bool | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class SuiteResult(BaseModel):
    suite: str
    metrics: dict[str, float]
    thresholds: dict[str, float]
    per_scenario: list[ScenarioResult]
    passed: bool
    prompt_versions: dict[str, str]
    started_at: str
    completed_at: str
    key_metric: str
    key_threshold: float
    key_observed: float


class EvalContext(BaseModel):
    """Per-run context passed into suites."""

    verbose: bool = False
    save_snapshots: bool = False
    output_dir: str | None = None
    snapshot_records: list[dict[str, Any]] = Field(default_factory=list)


class EvalSuite(ABC):
    name: str
    key_metric: str

    @abstractmethod
    def thresholds(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    async def run(self, dataset: list[TaggedScenario], ctx: EvalContext) -> SuiteResult:
        raise NotImplementedError
