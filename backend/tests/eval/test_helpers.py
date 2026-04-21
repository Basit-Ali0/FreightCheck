"""Eval helper normalization and stats."""

from __future__ import annotations

from eval.helpers import (
    currency_grounds_in_text,
    percentile,
    string_grounds_in_text,
    values_equal,
)


def test_values_equal_strings() -> None:
    assert values_equal("Acme Ltd", "  ACME LTD ")
    assert not values_equal("a", "b")


def test_values_equal_float_tolerance() -> None:
    assert values_equal(100.0, 100.05)
    assert not values_equal(100.0, 102.0)


def test_percentile() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert percentile(xs, 0.5) == 3.0


def test_grounding_helpers() -> None:
    raw = "Total USD 1,234.56 for shipment CNY context RMB"
    assert currency_grounds_in_text("USD", raw)
    assert string_grounds_in_text("shipment", raw)
