"""Evaluate the versioned deterministic rules against generated ground truth."""

import argparse
import csv
import json
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.features.audit.rules import RULE_VERSION, SEVERITY, evaluate
from app.features.ingestion.models import ImportRow, Purchase
from app.features.ingestion.parsing import normalize
from generate_synthetic import SIZES, generate


def evaluate_size(size: int, seed: int, output_dir: Path) -> dict[str, object]:
    csv_path, truth_path = generate(size, seed, output_dir)
    truth = json.loads(truth_path.read_text(encoding="utf-8"))["rules"]
    organization_id = uuid.uuid5(uuid.NAMESPACE_URL, f"processmind:{seed}:organization")
    batch_id = uuid.uuid5(uuid.NAMESPACE_URL, f"processmind:{seed}:{size}:batch")
    purchases: list[Purchase] = []
    rejected: list[ImportRow] = []
    source_numbers: dict[uuid.UUID, int] = {}
    with csv_path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError("missing_headers")
        mapping = {field: field for field in reader.fieldnames}
        for number, raw in enumerate(reader, start=2):
            values, errors = normalize(raw, mapping)
            row_id = uuid.uuid5(batch_id, f"row:{number}")
            source_numbers[row_id] = number
            if errors:
                rejected.append(
                    ImportRow(
                        id=row_id,
                        organization_id=organization_id,
                        batch_id=batch_id,
                        row_number=number,
                        raw_json=raw,
                        normalized_json=None,
                        errors=errors,
                    )
                )
                continue
            purchase_id = uuid.uuid5(batch_id, f"purchase:{number}")
            source_numbers[purchase_id] = number
            purchases.append(
                Purchase(
                    id=purchase_id,
                    organization_id=organization_id,
                    batch_id=batch_id,
                    import_row_id=row_id,
                    supplier_id=uuid.uuid5(organization_id, values["supplier_id"]),
                    external_purchase_id=values["purchase_id"],
                    product_id=values["product_id"],
                    product_name=values.get("product_name") or None,
                    purchase_date=date.fromisoformat(values["purchase_date"]),
                    quantity=Decimal(values["quantity"]),
                    unit_of_measure=values.get("unit_of_measure") or None,
                    unit_price=Decimal(values["unit_price"]),
                    declared_total=Decimal(values["total_amount"]),
                    currency=values["currency"],
                    expected_delivery_date=date.fromisoformat(
                        values["expected_delivery_date"]
                    )
                    if values.get("expected_delivery_date")
                    else None,
                    actual_delivery_date=date.fromisoformat(
                        values["actual_delivery_date"]
                    )
                    if values.get("actual_delivery_date")
                    else None,
                )
            )
    findings, limitation = evaluate(purchases, rejected, {})
    detected: dict[str, set[int]] = {code: set() for code in SEVERITY}
    for finding in findings:
        if finding.code == "DUPLICATE":
            pair = [
                source_numbers[source.purchase_id]
                for source in finding.evidence
                if source.purchase_id is not None
            ]
            detected[finding.code].add(max(pair))
            continue
        else:
            source_id = (
                finding.evidence[0].purchase_id or finding.evidence[0].import_row_id
            )
        if source_id is not None:
            detected[finding.code].add(source_numbers[source_id])
    metrics: dict[str, dict[str, int | float | None]] = {}
    for code in SEVERITY:
        expected = set(truth[code])
        found = detected[code]
        tp = len(expected & found)
        fp = len(found - expected)
        fn = len(expected - found)
        metrics[code] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        }
    return {
        "size": size,
        "seed": seed,
        "rule_set_version": RULE_VERSION,
        "valid_purchases": len(purchases),
        "rejected_rows": len(rejected),
        "limitation": limitation,
        "metrics": metrics,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, choices=SIZES, default=SIZES)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("synthetic-output"))
    parser.add_argument("--assert-gates", action="store_true")
    args = parser.parse_args()
    for selected_size in args.sizes:
        result = evaluate_size(selected_size, args.seed, args.output_dir)
        print(json.dumps(result))
        if args.assert_gates and selected_size >= 1000:
            for code in (
                "DUPLICATE",
                "INVALID_QUANTITY",
                "LATE_DELIVERY",
                "INCOMPLETE_RECORD",
            ):
                score = result["metrics"][code]
                if score["fp"] or score["fn"]:
                    raise SystemExit(
                        f"Ground truth gate failed: {code} at {selected_size}"
                    )
