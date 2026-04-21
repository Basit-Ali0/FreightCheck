"""Generate custom test PDFs with intentional discrepancies for manual testing."""

import sys
from pathlib import Path

# Add the parent level so eval can be imported
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from eval.synthetic_generator import ShipmentScenario, _random_truth, generate_pdfs  # noqa: E402


def make_scenario_1_weight_container(seed: int) -> dict[str, bytes]:
    # Issue 1: Weight mismatch and Container mismatch
    truth = _random_truth(seed)
    
    # Intentionally modify the PL overrides to create exceptions
    pl_overrides = {
        "total_weight": truth.gross_weight_kg - 500.0, # 500 kg off
        "container_numbers": list(truth.container_numbers) + ["MSKU9999999"] # noqa: RUF005, E501
    }
    
    scenario = ShipmentScenario(
        truth=truth,
        scenario_kind="weight_container_mismatch",
        packing_list_overrides=pl_overrides
    )
    return generate_pdfs(scenario, seed)

def make_scenario_2_incoterm_value(seed: int) -> dict[str, bytes]:
    # Issue 2: Incoterm plausibility and Invoice sum mismatch
    truth = _random_truth(seed)
    
    # Overrides for Invoice and BoL
    inv_overrides = {
        "incoterm": "FOB", 
        "total_value": sum(li.quantity * li.unit_price for li in truth.line_items) + 1500.0 # line items won't sum correctly  # noqa: E501
    }
    bol_overrides = {
        "port_of_loading": "" # FOB requires a port of loading!
    }
    
    scenario = ShipmentScenario(
        truth=truth,
        scenario_kind="incoterm_value_mismatch",
        invoice_overrides=inv_overrides,
        bol_overrides=bol_overrides
    )
    return generate_pdfs(scenario, seed)

def make_scenario_3_semantic(seed: int) -> dict[str, bytes]:
    # Issue 3: Minor semantic mismatches
    truth = _random_truth(seed)
    
    bol_overrides = {
        "shipper": truth.shipper + " Exporters LLC",
        "description_of_goods": "Industrial Medical Equipment Batch"
    }
    inv_overrides = {
        "seller": truth.shipper + " Trading Bureau",
        # Alter the first line item description to be very different
    }
    
    scenario = ShipmentScenario(
        truth=truth,
        scenario_kind="semantic_mismatch",
        bol_overrides=bol_overrides,
        invoice_overrides=inv_overrides
    )
    
    # Line items override is nested, so we need a cleaner way to override description
    # We will just inject some text or override the entire line_items in truth for Invoice
    modified_items = []
    for li in truth.line_items:
        import copy  # noqa: PLC0415
        new_li = copy.copy(li)
        new_li.description = "Surgical Tools and Instruments"
        modified_items.append({"description": new_li.description, "quantity": new_li.quantity, "unit_price": new_li.unit_price})  # noqa: E501
    
    scenario.invoice_overrides["line_items"] = modified_items
    
    return generate_pdfs(scenario, seed)

if __name__ == "__main__":
    out_dir = Path("tests/fixtures/pdfs/issue_tests")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    scenarios = {
        "1_weight_container_mismatch": make_scenario_1_weight_container(100),
        "2_incoterm_value_mismatch": make_scenario_2_incoterm_value(200),
        "3_semantic_mismatch": make_scenario_3_semantic(300)
    }
    
    for name, pdfs in scenarios.items():
        scenario_dir = out_dir / name
        scenario_dir.mkdir(exist_ok=True)
        for doc_type, pdf_bytes in pdfs.items():
            dest = scenario_dir / f"{doc_type}.pdf"
            dest.write_bytes(pdf_bytes)
            print(f"Written: {dest}")  # noqa: T201
            
    print(f"\nSuccessfully generated 3 issue scenarios in {out_dir.resolve()}")  # noqa: T201
