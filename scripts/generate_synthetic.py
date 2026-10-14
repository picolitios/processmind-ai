"""Generate reproducible purchase CSV and ground truth for Phase 3 fixtures."""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

SIZES = (100, 1_000, 10_000, 50_000)
HEADERS = (
    "purchase_id",
    "supplier_id",
    "supplier_name",
    "purchase_date",
    "product_id",
    "product_name",
    "quantity",
    "unit_of_measure",
    "unit_price",
    "currency",
    "total_amount",
    "expected_delivery_date",
    "actual_delivery_date",
)


def generate(size: int, seed: int, output_dir: Path) -> tuple[Path, Path]:
    if size not in SIZES:
        raise ValueError(f"size must be one of {SIZES}")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"purchases_{size}_{seed}.csv"
    truth_path = output_dir / f"purchases_{size}_{seed}.truth.json"
    randomizer = random.Random(seed)
    truth: dict[str, list[int]] = {
        "normal": [],
        "duplicate": [],
        "overprice": [],
        "delay": [],
        "invalid": [],
    }
    rule_truth: dict[str, list[int]] = {
        "DUPLICATE": [],
        "TOTAL_MISMATCH": [],
        "INVALID_QUANTITY": [],
        "PRICE_OUTLIER": [],
        "INVALID_DATES": [],
        "LATE_DELIVERY": [],
        "RECURRING_DELAY": [],
        "INCOMPLETE_RECORD": [],
        "OVER_LIMIT": [],
    }
    base = date(2025, 1, 1)
    last_normal: dict[str, object] | None = None
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=HEADERS)
        writer.writeheader()
        for index in range(1, size + 1):
            label = (
                "invalid"
                if index % 97 == 0
                else "duplicate"
                if index % 53 == 0
                else "overprice"
                if index % 47 == 0
                else "delay"
                if index % 41 == 0
                else "normal"
            )
            truth[label].append(index + 1)  # physical CSV row, including header
            product = 1 + randomizer.randrange(20)
            purchased = base + timedelta(days=index % 365)
            expected = purchased + timedelta(days=7)
            price = Decimal(125 if label == "overprice" else 10 + product)
            quantity = (
                Decimal(1 + randomizer.randrange(8)) + Decimal(index // 365) / 1000
            )
            row: dict[str, object] = {
                "purchase_id": f"P-{index:06d}",
                "supplier_id": f"S-{1 + index % 12:03d}",
                "supplier_name": f"Supplier {1 + index % 12}",
                "purchase_date": purchased.isoformat(),
                "product_id": f"SKU-{product:03d}",
                "product_name": f"Product {product}",
                "quantity": quantity,
                "unit_of_measure": "EA",
                "unit_price": price,
                "currency": "BRL",
                "total_amount": (price * quantity).quantize(Decimal("0.01")),
                "expected_delivery_date": expected.isoformat(),
                "actual_delivery_date": (
                    expected + timedelta(days=12) if label == "delay" else expected
                ).isoformat(),
            }
            if label == "duplicate" and last_normal is not None:
                row = {**last_normal, "purchase_id": row["purchase_id"]}
                rule_truth["DUPLICATE"].append(index + 1)
            elif label == "overprice":
                rule_truth["PRICE_OUTLIER"].append(index + 1)
            elif label == "delay":
                rule_truth["LATE_DELIVERY"].append(index + 1)
            elif label == "invalid":
                if index % 2:
                    row["quantity"] = 0
                    rule_truth["INVALID_QUANTITY"].append(index + 1)
                else:
                    row["product_id"] = ""
                rule_truth["INCOMPLETE_RECORD"].append(index + 1)
            else:
                last_normal = row.copy()
            writer.writerow(row)
    truth_path.write_text(
        json.dumps(
            {"seed": seed, "size": size, "rows": truth, "rules": rule_truth}, indent=2
        ),
        encoding="utf-8",
    )
    return csv_path, truth_path


def generate_xlsx(csv_path: Path) -> Path:
    from openpyxl import Workbook

    xlsx_path = csv_path.with_suffix(".xlsx")
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Purchases")
    with csv_path.open(encoding="utf-8", newline="") as source:
        for row in csv.reader(source):
            sheet.append(row)
    workbook.save(xlsx_path)
    return xlsx_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, choices=SIZES, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("synthetic-output"))
    parser.add_argument("--xlsx", action="store_true")
    args = parser.parse_args()
    csv_path, truth_path = generate(args.size, args.seed, args.output_dir)
    print(csv_path, truth_path, sep="\n")
    if args.xlsx:
        print(generate_xlsx(csv_path))
