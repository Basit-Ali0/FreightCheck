"""Deterministic synthetic shipping PDFs for evaluation (Evaluation Spec §1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from random import Random
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# ---- ISO 6346 (from python-stdnum, LGPL) ---------------------------------

_ISO_ALPHABET = "0123456789A BCDEFGHIJK LMNOPQRSTU VWXYZ"


def _iso6346_compact(number: str) -> str:
    return "".join(c for c in number.upper() if c not in " \t\r\n")


def iso6346_calc_check_digit(prefix10: str) -> str:
    """Return check digit for the first 10 characters (owner+category+serial)."""
    number = _iso6346_compact(prefix10)
    return str(
        sum(_ISO_ALPHABET.index(n) * pow(2, i) for i, n in enumerate(number)) % 11 % 10,
    )


def make_container_id(owner3: str, serial6: str) -> str:
    """Build an 11-char ISO 6346 container id (owner + U + serial + check)."""
    owner = owner3.upper()[:3].ljust(3, "X")
    digits = "".join(ch for ch in serial6 if ch.isdigit())[:6].zfill(6)
    prefix10 = f"{owner}U{digits}"
    return prefix10 + iso6346_calc_check_digit(prefix10)


def pin_pdf_metadata(pdf_bytes: bytes) -> bytes:
    """Normalize volatile PDF trailer fields so same layout yields identical bytes."""
    out = pdf_bytes
    out = re.sub(
        rb"/CreationDate\s*\([^)]*\)",
        rb"/CreationDate (D:20000101000000+00'00')",
        out,
    )
    out = re.sub(
        rb"/ModDate\s*\([^)]*\)",
        rb"/ModDate (D:20000101000000+00'00')",
        out,
    )
    out = re.sub(
        rb"/ID\s*\[\s*<[^>]+>\s*<[^>]+>\s*\]",
        rb"/ID [<00112233445566778899aabbccddeeff><00112233445566778899aabbccddeeff>]",
        out,
    )
    return out  # noqa: RET504


# ---- Domain dataclasses ----------------------------------------------------


@dataclass
class LineItemTruth:
    description: str
    quantity: int
    unit_price: float
    net_weight_kg: float


@dataclass
class ShipmentTruth:
    """Ground truth shared across the three documents."""

    bol_number: str
    invoice_number: str
    shipper: str
    consignee: str
    vessel: str
    pol: str
    pod: str
    incoterm: str
    container_numbers: list[str]
    description: str
    gross_weight_kg: float
    total_packages: int
    line_items: list[LineItemTruth]
    total_value: float
    currency: str
    invoice_date: str


@dataclass
class ShipmentScenario:
    """Shipment plus optional per-document overrides and injections."""

    truth: ShipmentTruth
    bol_overrides: dict[str, Any] = field(default_factory=dict)
    invoice_overrides: dict[str, Any] = field(default_factory=dict)
    packing_list_overrides: dict[str, Any] = field(default_factory=dict)
    injected_text: dict[str, str] = field(default_factory=dict)
    scenario_kind: str = "consistent"
    low_quality: bool = False
    invoice_omit_fields: frozenset[str] = frozenset()


def _random_truth(seed: int) -> ShipmentTruth:
    rng = Random(seed)
    owner = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    serial = "".join(rng.choice("0123456789") for _ in range(6))
    c2_owner = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    c2_serial = "".join(rng.choice("0123456789") for _ in range(6))
    containers = [
        make_container_id(owner, serial),
        make_container_id(c2_owner, c2_serial),
    ]
    incoterm = rng.choice(["FOB", "CIF", "DDP", "FCA"])
    n_items = rng.randint(1, 3)
    items: list[LineItemTruth] = []
    for i in range(n_items):
        desc = f"Widget-{seed}-{i} {rng.choice(['Steel', 'Fabric', 'Parts'])}"
        qty = rng.randint(5, 500)
        unit = round(rng.uniform(1.5, 99.99), 2)
        net = round(rng.uniform(10.0, 5000.0), 2)
        items.append(
            LineItemTruth(description=desc, quantity=qty, unit_price=unit, net_weight_kg=net)
        )  # noqa: E501
    total_qty = sum(li.quantity for li in items)
    total_value = round(sum(li.quantity * li.unit_price for li in items), 2)
    total_packages = max(1, total_qty // rng.randint(2, 8))
    gross = round(sum(li.net_weight_kg for li in items) * rng.uniform(1.01, 1.08), 2)
    bol_number = f"BOL-{seed:07d}-{rng.randint(0, 9999):04d}"
    invoice_number = f"INV-{seed:07d}-{rng.randint(0, 9999):04d}"
    shipper = f"{rng.choice(['Acme', 'Globex', 'Initech'])} {rng.choice(['Exports', 'Trading', 'Logistics'])} Ltd"  # noqa: E501
    consignee = f"{rng.choice(['Contoso', 'Umbrella', 'Stark'])} {rng.choice(['Imports', 'Retail', 'Industries'])} LLC"  # noqa: E501
    vessel = f"MV {rng.choice(['Horizon', 'Pacific', 'Atlas'])} {rng.randint(100, 999)}"
    pol = rng.choice(["Shanghai", "Ningbo", "Singapore", "Rotterdam"])
    pod = rng.choice(["Los Angeles", "Hamburg", "Felixstowe", "Dubai"])
    desc = f"Industrial goods batch {seed}"
    currency = rng.choice(["USD", "EUR", "GBP"])
    year = 2024 + (seed % 2)
    month = 1 + (seed % 12)
    day = 1 + (seed % 28)
    invoice_date = f"{year:04d}-{month:02d}-{day:02d}"
    return ShipmentTruth(
        bol_number=bol_number,
        invoice_number=invoice_number,
        shipper=shipper,
        consignee=consignee,
        vessel=vessel,
        pol=pol,
        pod=pod,
        incoterm=incoterm,
        container_numbers=containers,
        description=desc,
        gross_weight_kg=gross,
        total_packages=total_packages,
        line_items=items,
        total_value=total_value,
        currency=currency,
        invoice_date=invoice_date,
    )


def truth_with_line_items(seed: int, count: int) -> ShipmentTruth:
    """Build a shipment with exactly ``count`` harmonised line items (stress path)."""
    rng = Random(seed)
    owner = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    serial = "".join(rng.choice("0123456789") for _ in range(6))
    containers = [make_container_id(owner, serial)]
    items: list[LineItemTruth] = []
    for i in range(count):
        desc = f"SKU-{seed:05d}-{i:03d} Cotton piece goods"
        qty = 10 + (i % 7)
        unit = round(5.0 + (i % 50) * 1.11, 2)
        net = round(50.0 + i * 3.7, 2)
        items.append(
            LineItemTruth(description=desc, quantity=qty, unit_price=unit, net_weight_kg=net)
        )  # noqa: E501
    total_qty = sum(li.quantity for li in items)
    total_value = round(sum(li.quantity * li.unit_price for li in items), 2)
    total_packages = max(1, total_qty // 5)
    gross = round(sum(li.net_weight_kg for li in items) * 1.02, 2)
    bol_number = f"BOL-DUP-{seed:07d}"
    invoice_number = f"INV-DUP-{seed:07d}"
    return ShipmentTruth(
        bol_number=bol_number,
        invoice_number=invoice_number,
        shipper="Acme Exports Ltd",
        consignee="Contoso Imports LLC",
        vessel="MV StressTest 1",
        pol="Shanghai",
        pod="Los Angeles",
        incoterm="FOB",
        container_numbers=containers,
        description="Industrial goods batch (duplicate line stress)",
        gross_weight_kg=gross,
        total_packages=total_packages,
        line_items=items,
        total_value=total_value,
        currency="USD",
        invoice_date="2026-03-15",
    )


def _degrade_line(text: str, rng: Random) -> str:
    """Inject deterministic OCR-like noise."""
    out: list[str] = []
    for ch in text:
        if ch.isalnum() and rng.random() < 0.04:  # noqa: PLR2004
            out.append(ch + rng.choice(["", "|", ""]))
        elif ch == " " and rng.random() < 0.06:  # noqa: PLR2004
            out.append("  ")
        else:
            out.append(ch)
    return "".join(out)


def _truth_as_dicts(
    truth: ShipmentTruth,
    bol_o: dict[str, Any],
    inv_o: dict[str, Any],
    pl_o: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bol = {
        "bill_of_lading_number": truth.bol_number,
        "shipper": truth.shipper,
        "consignee": truth.consignee,
        "vessel_name": truth.vessel,
        "port_of_loading": truth.pol,
        "port_of_discharge": truth.pod,
        "container_numbers": list(truth.container_numbers),
        "description_of_goods": truth.description,
        "gross_weight": truth.gross_weight_kg,
        "incoterm": truth.incoterm,
    }
    invoice_li = [
        {
            "description": li.description,
            "quantity": li.quantity,
            "unit_price": li.unit_price,
        }
        for li in truth.line_items
    ]
    pl_li = [
        {"description": li.description, "quantity": li.quantity, "net_weight": li.net_weight_kg}
        for li in truth.line_items
    ]
    invoice = {
        "invoice_number": truth.invoice_number,
        "seller": truth.shipper,
        "buyer": truth.consignee,
        "invoice_date": truth.invoice_date,
        "line_items": invoice_li,
        "total_value": truth.total_value,
        "currency": truth.currency,
        "incoterm": truth.incoterm,
    }
    pl = {
        "total_packages": truth.total_packages,
        "total_weight": truth.gross_weight_kg,
        "container_numbers": list(truth.container_numbers),
        "line_items": pl_li,
    }
    for k, v in bol_o.items():
        bol[k] = v
    for k, v in inv_o.items():
        invoice[k] = v
    for k, v in pl_o.items():
        pl[k] = v
    return bol, invoice, pl


def _render_canvas(lines: list[str], seed: int) -> bytes:  # noqa: ARG001
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("FreightCheck Synthetic")
    c.setAuthor("FreightCheck Eval")
    c.setSubject("synthetic")
    c.setCreator("FreightCheck eval harness")
    width, height = A4  # noqa: RUF059
    y = height - 40
    c.setFont("Helvetica", 10)
    for line in lines:
        if y < 40:  # noqa: PLR2004
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 40
        c.drawString(40, y, line[:500])
        y -= 14
    c.showPage()
    c.save()
    raw = buf.getvalue()
    return pin_pdf_metadata(raw)


def _lines_from_doc(
    title: str, fields: dict[str, Any], rng: Random, low_quality: bool
) -> list[str]:  # noqa: E501
    lines = [title, "===", ""]
    for key in sorted(fields.keys()):
        val = fields[key]
        if isinstance(val, list):
            lines.append(f"{key}:")
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    lines.append(f"  - item_{i}:")
                    for ik in sorted(item.keys()):
                        line = f"      {ik}: {item[ik]}"
                        lines.append(_degrade_line(line, rng) if low_quality else line)
                else:
                    line = f"  - {item}"
                    lines.append(_degrade_line(line, rng) if low_quality else line)
        else:
            line = f"{key}: {val}"
            lines.append(_degrade_line(line, rng) if low_quality else line)
    return lines


def generate_pdfs(scenario: ShipmentScenario, seed: int) -> dict[str, bytes]:
    """Return in-memory PDF bytes for bol / invoice / packing_list."""
    rng = Random(seed + 7919)
    bol_f, inv_f, pl_f = _truth_as_dicts(
        scenario.truth,
        scenario.bol_overrides,
        scenario.invoice_overrides,
        scenario.packing_list_overrides,
    )
    # Missing-field handling: omit keys entirely from rendered invoice
    if scenario.invoice_omit_fields:
        inv_f = {k: v for k, v in inv_f.items() if k not in scenario.invoice_omit_fields}

    bol_lines = _lines_from_doc("BILL OF LADING", bol_f, rng, scenario.low_quality)
    inv_lines = _lines_from_doc("COMMERCIAL INVOICE", inv_f, rng, scenario.low_quality)
    pl_lines = _lines_from_doc("PACKING LIST", pl_f, rng, scenario.low_quality)

    for doc_key, blob in scenario.injected_text.items():
        if doc_key == "bol":
            bol_lines.extend(["", "NOTES:", blob])
        elif doc_key == "invoice":
            inv_lines.extend(["", "NOTES:", blob])
        elif doc_key == "packing_list":
            pl_lines.extend(["", "NOTES:", blob])

    return {
        "bol": _render_canvas(bol_lines, seed),
        "invoice": _render_canvas(inv_lines, seed + 1),
        "packing_list": _render_canvas(pl_lines, seed + 2),
    }
