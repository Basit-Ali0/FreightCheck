"""Shared PDF → raw text → extract_all path for extraction suites."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.datasets import TaggedScenario
from eval.suites.base import EvalContext
from eval.synthetic_generator import generate_pdfs
from freightcheck.agent.graph import make_initial_state
from freightcheck.agent.nodes.extract_all import extract_all
from freightcheck.services.pdf_parser import extract_raw_text


async def raw_texts_from_tagged(tagged: TaggedScenario) -> dict[str, str]:
    pdfs = generate_pdfs(tagged.scenario, tagged.pdf_seed)
    return {k: extract_raw_text(v) for k, v in pdfs.items()}


async def run_extract_all_for_tagged(
    tagged: TaggedScenario,
    *,
    ctx: EvalContext,
    snapshot_suite: str,
) -> dict[str, Any]:
    raw_texts = await raw_texts_from_tagged(tagged)
    state = make_initial_state(tagged.scenario_id, raw_texts)
    out = await extract_all(state)
    if ctx.save_snapshots and ctx.output_dir and snapshot_suite:
        snap_dir = Path(ctx.output_dir) / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "scenario_id": tagged.scenario_id,
            "suite": snapshot_suite,
            "raw_texts": {k: v[:8000] for k, v in raw_texts.items()},
            "extract_all": out,
        }
        (snap_dir / f"{tagged.scenario_id}_{snapshot_suite}.json").write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    return {"raw_texts": raw_texts, "extract": out}
