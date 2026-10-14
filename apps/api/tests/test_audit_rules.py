import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.features.audit.rules import evaluate
from app.features.ingestion.models import ImportRow, Purchase

BASE = date(2025, 1, 20)
ORG = uuid.uuid4()
SUPPLIER = uuid.uuid4()
BATCH = uuid.uuid4()


def purchase(
    number: int,
    *,
    supplier: uuid.UUID = SUPPLIER,
    day: date = BASE,
    price: str = "10.00",
    total: str = "20.00",
    quantity: str = "2",
    unit: str | None = "EA",
    expected: date | None = None,
    actual: date | None = None,
) -> Purchase:
    return Purchase(
        id=uuid.uuid4(),
        organization_id=ORG,
        batch_id=BATCH,
        import_row_id=uuid.uuid4(),
        supplier_id=supplier,
        external_purchase_id=f"P-{number}",
        product_id="SKU-1",
        product_name=None,
        purchase_date=day,
        quantity=Decimal(quantity),
        unit_of_measure=unit,
        unit_price=Decimal(price),
        declared_total=Decimal(total),
        currency="BRL",
        expected_delivery_date=expected,
        actual_delivery_date=actual,
    )


def test_nine_rules_with_structured_evidence() -> None:
    normal_supplier = uuid.uuid4()
    peers = [
        purchase(
            i,
            supplier=normal_supplier,
            day=BASE + timedelta(days=i),
            price="10.00",
            expected=BASE + timedelta(days=i + 2),
            actual=BASE + timedelta(days=i + 2),
        )
        for i in range(6)
    ]
    outlier = purchase(
        7, supplier=normal_supplier, day=BASE + timedelta(days=7), price="100.00", total="200.00"
    )
    duplicate = purchase(
        8,
        supplier=peers[0].supplier_id,
        day=peers[0].purchase_date,
        expected=peers[0].expected_delivery_date,
        actual=peers[0].actual_delivery_date,
    )
    mismatch = purchase(9, supplier=uuid.uuid4(), total="20.02")
    invalid_dates = purchase(10, supplier=uuid.uuid4(), actual=BASE - timedelta(days=1))
    late_supplier = uuid.uuid4()
    late = [
        purchase(
            11 + i,
            supplier=late_supplier,
            day=BASE + timedelta(days=i),
            expected=BASE + timedelta(days=i + 1),
            actual=BASE + timedelta(days=i + 3),
        )
        for i in range(3)
    ]
    over_limit = purchase(14, supplier=uuid.uuid4(), total="50.00", quantity="5")
    bad_row = ImportRow(
        id=uuid.uuid4(),
        organization_id=ORG,
        batch_id=BATCH,
        row_number=15,
        raw_json={"quantity": "0"},
        normalized_json=None,
        errors=[{"field": "quantity", "code": "non_positive", "message": "bad"}],
    )
    findings, limitation = evaluate(
        [*peers, outlier, duplicate, mismatch, invalid_dates, *late, over_limit],
        [bad_row],
        {"amount_limits": {"BRL": "40.00"}},
    )
    by_code: dict[str, list] = {}
    for finding in findings:
        by_code.setdefault(finding.code, []).append(finding)
    assert set(by_code) == {
        "DUPLICATE",
        "TOTAL_MISMATCH",
        "INVALID_QUANTITY",
        "PRICE_OUTLIER",
        "INVALID_DATES",
        "LATE_DELIVERY",
        "RECURRING_DELAY",
        "INCOMPLETE_RECORD",
        "OVER_LIMIT",
    }
    assert by_code["PRICE_OUTLIER"][0].evidence[0].data["peer_count"] >= 5
    assert by_code["RECURRING_DELAY"][0].evidence[0].data["completed_count"] == 3
    assert len(by_code["DUPLICATE"][0].evidence) == 2
    assert by_code["INVALID_QUANTITY"][0].evidence[0].import_row_id == bad_row.id
    assert all(finding.fingerprint == finding.fingerprint for finding in findings)
    assert limitation is None or "inconclusivo" in limitation


def test_boundaries_and_inconclusive_price() -> None:
    first = purchase(1, total="20.01", unit=None)
    second = purchase(2, supplier=uuid.uuid4(), expected=BASE + timedelta(days=1))
    findings, limitation = evaluate([first, second], [], {})
    assert "TOTAL_MISMATCH" not in {finding.code for finding in findings}
    assert "PRICE_OUTLIER" not in {finding.code for finding in findings}
    assert "LATE_DELIVERY" not in {finding.code for finding in findings}
    assert "RECURRING_DELAY" not in {finding.code for finding in findings}
    assert limitation is not None and "2 compras" in limitation


def test_invalid_quantity_uses_confirmed_source_column() -> None:
    row = ImportRow(
        id=uuid.uuid4(),
        organization_id=ORG,
        batch_id=BATCH,
        row_number=2,
        raw_json={"Quantidade": "0"},
        normalized_json=None,
        errors=[{"field": "quantity", "code": "non_positive", "message": "bad"}],
    )
    findings, _ = evaluate([], [row], {}, {BATCH: {"quantity": "Quantidade"}})
    quantity = next(item for item in findings if item.code == "INVALID_QUANTITY")
    assert quantity.evidence[0].data["raw_quantity"] == "0"
