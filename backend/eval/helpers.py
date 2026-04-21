"""Shared eval helpers: compare, grounding, stats, git metadata."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any


def git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return out.decode().strip()[:40]
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def normalize_string(s: str) -> str:
    return " ".join(s.lower().split())


def values_equal(truth: Any, extracted: Any) -> bool:  # noqa: PLR0911, PLR0912
    """Field comparison rules (Evaluation Spec §2.1)."""
    if truth is None and extracted is None:
        return True
    if truth is None or extracted is None:
        return False
    if isinstance(truth, bool) or isinstance(extracted, bool):
        return bool(truth) == bool(extracted)
    if isinstance(truth, str) and isinstance(extracted, str):
        return normalize_string(truth) == normalize_string(extracted)
    if isinstance(truth, int) and isinstance(extracted, (int, float)):
        return int(truth) == int(extracted)
    if isinstance(truth, float) and isinstance(extracted, (int, float)):
        a, b = float(truth), float(extracted)
        if a == b:
            return True
        denom = max(abs(a), abs(b), 1e-9)
        return abs(a - b) / denom <= 0.001  # noqa: PLR2004
    if isinstance(truth, list) and isinstance(extracted, list):
        if not truth and not extracted:
            return True
        if len(truth) != len(extracted):
            return False
        if truth and isinstance(truth[0], str):
            return {normalize_string(x) for x in truth} == {normalize_string(str(x)) for x in extracted}  # noqa: E501
        return all(values_equal(t, e) for t, e in zip(truth, extracted, strict=True))
    if isinstance(truth, dict) and isinstance(extracted, dict):
        if set(truth.keys()) != set(extracted.keys()):
            return False
        return all(values_equal(truth[k], extracted[k]) for k in truth)
    return truth == extracted


def truth_to_extracted_shape(truth: Any) -> dict[str, Any]:
    """Map ShipmentTruth dataclass to nested dict matching extractor keys."""
    from dataclasses import asdict  # noqa: PLC0415

    from eval.synthetic_generator import ShipmentTruth  # noqa: PLC0415

    if not isinstance(truth, ShipmentTruth):
        raise TypeError("expected ShipmentTruth")
    d = asdict(truth)
    bol = {
        "bill_of_lading_number": d["bol_number"],
        "shipper": d["shipper"],
        "consignee": d["consignee"],
        "vessel_name": d["vessel"],
        "port_of_loading": d["pol"],
        "port_of_discharge": d["pod"],
        "container_numbers": d["container_numbers"],
        "description_of_goods": d["description"],
        "gross_weight": d["gross_weight_kg"],
        "incoterm": d["incoterm"],
    }
    invoice_li = [
        {"description": li["description"], "quantity": li["quantity"], "unit_price": li["unit_price"]}  # noqa: E501
        for li in d["line_items"]
    ]
    pl_li = [
        {
            "description": li["description"],
            "quantity": li["quantity"],
            "net_weight": li["net_weight_kg"],
        }
        for li in d["line_items"]
    ]
    invoice = {
        "invoice_number": d["invoice_number"],
        "seller": d["shipper"],
        "buyer": d["consignee"],
        "invoice_date": d["invoice_date"],
        "line_items": invoice_li,
        "total_value": d["total_value"],
        "currency": d["currency"],
        "incoterm": d["incoterm"],
    }
    pl = {
        "total_packages": d["total_packages"],
        "total_weight": d["gross_weight_kg"],
        "container_numbers": d["container_numbers"],
        "line_items": pl_li,
    }
    return {"bol": bol, "invoice": invoice, "packing_list": pl}


def percentile(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    xs = sorted(sorted_vals)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return float(xs[f])
    return float(xs[f] + (xs[c] - xs[f]) * (k - f))


def token_overlap(a: str, b: str) -> float:
    ta = normalize_string(a).split()
    tb = normalize_string(b).split()
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / max(union, 1)


def _digits_only(s: str) -> str:
    return re.sub(r"\D+", "", s)


def number_grounds_in_text(num: float | int, raw: str) -> bool:
    raw_digits = _digits_only(raw)
    s = str(num)
    if "." in s:
        whole, frac = s.split(".", 1)
        frac = frac.rstrip("0")
        variants = {_digits_only(whole + frac), _digits_only(s)}
    else:
        variants = {_digits_only(s)}
    for v in variants:
        if v and v in raw_digits:
            return True
    # tonne/kg style: 12.4 t vs 12400 kg — if both appear as substrings of normalized
    try:
        kg = float(num)
        tonnes = kg / 1000.0
        for candidate in (f"{tonnes:.3f}", f"{tonnes:.1f}"):
            if _digits_only(candidate) in raw_digits:
                return True
    except ValueError:
        pass
    return False


def date_grounds_in_text(iso_date: str, raw: str) -> bool:
    raw_l = raw.lower()
    iso_date = iso_date.strip()
    if iso_date in raw_l or iso_date.replace("-", "/") in raw_l:
        return True
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", iso_date)
    if m:
        y, mo, d = m.groups()
        alt = f"{d}/{mo}/{y}"
        if alt in raw or f"{d}-{mo}-{y}" in raw:
            return True
    return False


def currency_grounds_in_text(code: str, raw: str) -> bool:
    raw_u = raw.upper()
    code = code.upper()
    if code in raw_u:
        return True
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "CNY": "¥"}
    if sym.get(code) and sym[code] in raw:
        return True
    if code == "CNY" and "rmb" in raw.lower():  # noqa: SIM103
        return True
    return False


def string_grounds_in_text(val: str, raw: str) -> bool:
    if normalize_string(val) in normalize_string(raw):
        return True
    return token_overlap(val, raw) >= 0.8  # noqa: PLR2004


def extraction_is_grounded(doc: str, field_path: str, value: Any, raw_text: str) -> bool:  # noqa: PLR0911
    """Grounding rules (Evaluation Spec §2.3)."""
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return number_grounds_in_text(value, raw_text)
    if isinstance(value, str):
        if field_path.endswith("currency") or field_path.rsplit(".", maxsplit=1)[-1] == "currency":
            return currency_grounds_in_text(value, raw_text)
        if "date" in field_path.lower():
            return date_grounds_in_text(value, raw_text)
        return string_grounds_in_text(value, raw_text)
    if isinstance(value, list):
        if not value:
            return True
        if isinstance(value[0], str):
            return all(string_grounds_in_text(v, raw_text) for v in value)
        if isinstance(value[0], dict):
            return all(
                extraction_is_grounded(doc, f"{field_path}[{i}]", sub, raw_text)
                for i, sub in enumerate(value)
            )
    if isinstance(value, dict):
        return all(
            extraction_is_grounded(doc, f"{field_path}.{k}", v, raw_text)
            for k, v in value.items()
        )
    return False


def iter_extracted_leaf_paths(
    doc: str,
    obj: Any,
    prefix: str = "",
) -> Iterable[tuple[str, Any]]:
    """Yield ``(bol.field.path, value)`` style paths for grounding checks."""

    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            yield from iter_extracted_leaf_paths(doc, v, path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            path = f"{prefix}[{i}]"
            yield from iter_extracted_leaf_paths(doc, item, path)
    else:
        yield f"{doc}.{prefix}", obj


def expected_severity_for_kind(kind: str) -> str:
    mapping = {
        "incoterm_conflict": "critical",
        "quantity_mismatch": "critical",
        "weight_mismatch_outside_tolerance": "critical",
        "container_number_mismatch": "critical",
        "invalid_container_check_digit": "critical",
        "incoterm_port_contradiction": "critical",
        "description_semantic_mismatch": "critical",
        "duplicate_line_items": "warning",
    }
    return mapping.get(kind, "warning")
