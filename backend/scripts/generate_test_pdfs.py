"""Generate a set of test PDFs for manual E2E testing.

Usage:
    uv run python scripts/generate_test_pdfs.py [--seed 42] [--output tests/fixtures/pdfs]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eval.synthetic_generator import ShipmentScenario, _random_truth, generate_pdfs


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic shipping PDFs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument(
        "--output",
        type=str,
        default="tests/fixtures/pdfs",
        help="Output directory (default: tests/fixtures/pdfs)",
    )
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    truth = _random_truth(args.seed)
    scenario = ShipmentScenario(truth=truth)
    pdfs = generate_pdfs(scenario, args.seed)

    for doc_type, pdf_bytes in pdfs.items():
        dest = out / f"{doc_type}.pdf"
        dest.write_bytes(pdf_bytes)
        print(f"  OK {dest}  ({len(pdf_bytes):,} bytes)")  # noqa: T201

    print(f"\nDone — {len(pdfs)} PDFs written to {out.resolve()}")  # noqa: T201
    print(f"Shipment: {truth.bol_number} / {truth.invoice_number}")  # noqa: T201
    print(f"Shipper:  {truth.shipper}  →  Consignee: {truth.consignee}")  # noqa: T201


if __name__ == "__main__":
    main()
