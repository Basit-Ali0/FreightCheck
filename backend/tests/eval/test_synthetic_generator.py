"""Eval synthetic generator determinism."""

from __future__ import annotations

from eval.scenarios import consistent, incoterm_conflict
from eval.synthetic_generator import generate_pdfs, pin_pdf_metadata


def test_same_seed_pdf_bytes_identical() -> None:
    s = consistent(42)
    a = generate_pdfs(s, 99)
    b = generate_pdfs(s, 99)
    assert a["bol"] == b["bol"]
    assert a["invoice"] == b["invoice"]
    assert a["packing_list"] == b["packing_list"]


def test_different_scenario_seeds_differ() -> None:
    """Different ``_random_truth`` seeds change payload; PDF bytes follow."""
    a = generate_pdfs(consistent(1), 100)
    b = generate_pdfs(consistent(2), 100)
    assert a["bol"] != b["bol"] or a["invoice"] != b["invoice"]


def test_scenario_override_changes_rendered_bytes() -> None:
    seed = 7
    base = generate_pdfs(consistent(seed), seed)
    alt = generate_pdfs(incoterm_conflict(seed), seed)
    assert base["invoice"] != alt["invoice"]


def test_pin_pdf_metadata_idempotent() -> None:
    s = consistent(3)
    raw = generate_pdfs(s, 11)["bol"]
    p1 = pin_pdf_metadata(raw)
    p2 = pin_pdf_metadata(p1)
    assert p1 == p2
