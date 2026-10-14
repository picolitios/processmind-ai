"""Generate reproducible purchase CSV and ground truth for Phase 3 fixtures."""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

SIZES = (100, 1_000, 10_000, 50_000)
HEADERS = (
    "purchase_id", "supplier_id", "supplier_name", "purchase_date", "product_id",
    "product_name", "quantity", "unit_price", "currency", "total_amount",
    "expected_delivery_date", "actual_delivery_date",
)


def generate(size: int, seed: int, output_dir: Path) -> tuple[Path, Path]:
    if size not in SIZES:
        raise ValueError(f"size must be one of {SIZES}")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"purchases_{size}_{seed}.csv"
    truth_path = output_dir / f"purchases_{size}_{seed}.truth.json"
    randomizer = random.Random(seed)
    truth: dict[str, list[int]] = {
        "normal": [], "duplicate": [], "overprice": [], "delay": [], "invalid": []
    }
    base = date(2025, 1, 1)
    with csv_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=HEADERS)
        writer.writeheader()
        for index in range(1, size + 1):
            label = ("invalid" if index % 97 == 0 else
                     "duplicate" if index % 53 == 0 else
                     "overprice" if index % 47 == 0 else
                     "delay" if index % 41 == 0 else "normal")
            truth[label].append(index + 1)  # physical CSV row, including header
            product = 1 + randomizer.randrange(20)
            purchased = base + timedelta(days=index % 365)
            expected = purchased + timedelta(days=7)
            price = 125 if label == "overprice" else 10 + product
            quantity = 1 + randomizer.randrange(8)
            writer.writerow({
                "purchase_id": f"P-{index - 1 if label == 'duplicate' else index:06d}",
                "supplier_id": f"S-{1 + index % 12:03d}",
                "supplier_name": f"Supplier {1 + index % 12}",
                "purchase_date": purchased.isoformat(), "product_id": f"SKU-{product:03d}",
                "product_name": f"Product {product}",
                "quantity": "invalid" if label == "invalid" else quantity,
                "unit_price": price, "currency": "BRL", "total_amount": price * quantity,
                "expected_delivery_date": expected.isoformat(),
                "actual_delivery_date": (expected + timedelta(days=12)
                                         if label == "delay" else expected).isoformat(),
            })
    truth_path.write_text(json.dumps({"seed": seed, "size": size, "rows": truth}, indent=2),
                          encoding="utf-8")
    return csv_path, truth_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, choices=SIZES, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("synthetic-output"))
    args = parser.parse_args()
    print(*generate(args.size, args.seed, args.output_dir), sep="\n")
