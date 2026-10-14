import hashlib
import json
import uuid
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from app.features.ingestion.models import ImportRow, Purchase

RULE_VERSION = "1.0.0"
SEVERITY = {
    "DUPLICATE": "high",
    "TOTAL_MISMATCH": "medium",
    "INVALID_QUANTITY": "medium",
    "PRICE_OUTLIER": "medium",
    "INVALID_DATES": "medium",
    "LATE_DELIVERY": "low",
    "RECURRING_DELAY": "medium",
    "INCOMPLETE_RECORD": "low",
    "OVER_LIMIT": "high",
}
PRICE_MIN_PEERS = 5
PRICE_WINDOW_DAYS = 90


@dataclass(frozen=True)
class EvidenceDraft:
    data: dict[str, Any]
    purchase_id: uuid.UUID | None = None
    import_row_id: uuid.UUID | None = None


@dataclass(frozen=True)
class FindingDraft:
    code: str
    source_key: str
    explanation: str
    evidence: tuple[EvidenceDraft, ...]

    @property
    def fingerprint(self) -> str:
        raw = json.dumps([self.code, self.source_key], separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


def quartiles(values: list[Decimal]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    lower = ordered[:midpoint]
    upper = ordered[-midpoint:]
    center = median(ordered)
    q1 = median(lower)
    q3 = median(upper)
    mad = median([abs(value - center) for value in ordered])
    return center, q1, q3, mad


def evaluate(
    purchases: list[Purchase],
    rejected_rows: list[ImportRow],
    config: dict[str, Any],
    column_mappings: dict[uuid.UUID, dict[str, str]] | None = None,
) -> tuple[list[FindingDraft], str | None]:
    findings: list[FindingDraft] = []
    purchases = sorted(purchases, key=lambda item: (item.purchase_date, item.id))
    duplicates: dict[tuple[Any, ...], Purchase] = {}
    comparable: dict[tuple[str, str, str], list[Purchase]] = defaultdict(list)
    suppliers: dict[uuid.UUID, list[Purchase]] = defaultdict(list)
    for purchase in purchases:
        suppliers[purchase.supplier_id].append(purchase)
        if purchase.unit_of_measure:
            comparable[(purchase.product_id, purchase.currency, purchase.unit_of_measure)].append(
                purchase
            )
        key = (
            purchase.supplier_id,
            purchase.product_id,
            purchase.purchase_date,
            purchase.quantity,
            purchase.unit_of_measure,
            purchase.unit_price,
            purchase.declared_total,
            purchase.currency,
        )
        prior = duplicates.get(key)
        if prior is None:
            duplicates[key] = purchase
        else:
            findings.append(
                FindingDraft(
                    "DUPLICATE",
                    f"{prior.id}:{purchase.id}",
                    "Compras com fornecedor, produto, data, quantidade e valores iguais; "
                    "revisar contexto.",
                    (
                        EvidenceDraft(
                            {"role": "first", "purchase_id": prior.external_purchase_id}, prior.id
                        ),
                        EvidenceDraft(
                            {"role": "duplicate", "purchase_id": purchase.external_purchase_id},
                            purchase.id,
                        ),
                    ),
                )
            )

        calculated = purchase.quantity * purchase.unit_price
        difference = abs(purchase.declared_total - calculated)
        if difference > Decimal("0.01"):
            findings.append(
                FindingDraft(
                    "TOTAL_MISMATCH",
                    str(purchase.id),
                    "Total declarado diverge do cálculo.",
                    (
                        EvidenceDraft(
                            {
                                "declared_total": str(purchase.declared_total),
                                "calculated_total": str(calculated),
                                "difference": str(difference),
                                "currency": purchase.currency,
                            },
                            purchase.id,
                        ),
                    ),
                )
            )

        expected = purchase.expected_delivery_date
        actual = purchase.actual_delivery_date
        if (
            (expected is not None and expected < purchase.purchase_date)
            or (actual is not None and actual < purchase.purchase_date)
            or (actual is not None and expected is None)
        ):
            findings.append(
                FindingDraft(
                    "INVALID_DATES",
                    str(purchase.id),
                    "Datas de entrega incoerentes com a compra.",
                    (
                        EvidenceDraft(
                            {
                                "purchase_date": purchase.purchase_date.isoformat(),
                                "expected_delivery_date": expected.isoformat()
                                if expected
                                else None,
                                "actual_delivery_date": actual.isoformat() if actual else None,
                            },
                            purchase.id,
                        ),
                    ),
                )
            )
        elif expected is not None and actual is not None and actual > expected:
            findings.append(
                FindingDraft(
                    "LATE_DELIVERY",
                    str(purchase.id),
                    "Entrega concluída após a data prevista.",
                    (
                        EvidenceDraft(
                            {
                                "expected_delivery_date": expected.isoformat(),
                                "actual_delivery_date": actual.isoformat(),
                                "days_late": (actual - expected).days,
                            },
                            purchase.id,
                        ),
                    ),
                )
            )

        limit_text = config.get("amount_limits", {}).get(purchase.currency)
        if limit_text is not None:
            limit = Decimal(str(limit_text))
            if purchase.declared_total > limit:
                findings.append(
                    FindingDraft(
                        "OVER_LIMIT",
                        str(purchase.id),
                        "Total declarado supera o limite configurado.",
                        (
                            EvidenceDraft(
                                {
                                    "declared_total": str(purchase.declared_total),
                                    "limit": str(limit),
                                    "currency": purchase.currency,
                                },
                                purchase.id,
                            ),
                        ),
                    )
                )

    insufficient = 0
    comparable_dates = {
        key: [item.purchase_date for item in group] for key, group in comparable.items()
    }
    price_stats: dict[
        tuple[str, str, str, date, Decimal],
        tuple[int, Decimal, Decimal, Decimal, Decimal, Decimal] | None,
    ] = {}
    for purchase in purchases:
        unit = purchase.unit_of_measure
        if not unit:
            insufficient += 1
            continue
        group_key = (purchase.product_id, purchase.currency, unit)
        cache_key = (*group_key, purchase.purchase_date, purchase.unit_price)
        if cache_key not in price_stats:
            dates = comparable_dates[group_key]
            start_index = bisect_left(
                dates, purchase.purchase_date - timedelta(days=PRICE_WINDOW_DAYS)
            )
            end_index = bisect_right(
                dates, purchase.purchase_date + timedelta(days=PRICE_WINDOW_DAYS)
            )
            peers = [
                item.unit_price
                for item in comparable[group_key][start_index:end_index]
                if item.id != purchase.id
            ]
            if len(peers) < PRICE_MIN_PEERS:
                price_stats[cache_key] = None
            else:
                center, q1, q3, mad = quartiles(peers)
                margin = max(3 * (q3 - q1), Decimal("4.4478") * mad, center * Decimal("0.25"))
                price_stats[cache_key] = (len(peers), center, q1, q3, mad, margin)
        stats = price_stats[cache_key]
        if stats is None:
            insufficient += 1
            continue
        peer_count, center, q1, q3, mad, margin = stats
        if purchase.unit_price < center - margin or purchase.unit_price > center + margin:
            findings.append(
                FindingDraft(
                    "PRICE_OUTLIER",
                    str(purchase.id),
                    "Preço unitário fora da faixa de pares comparáveis; requer revisão.",
                    (
                        EvidenceDraft(
                            {
                                "unit_price": str(purchase.unit_price),
                                "median": str(center),
                                "q1": str(q1),
                                "q3": str(q3),
                                "mad": str(mad),
                                "margin": str(margin),
                                "peer_count": peer_count,
                                "window_days": PRICE_WINDOW_DAYS,
                                "product_id": purchase.product_id,
                                "currency": purchase.currency,
                                "unit_of_measure": unit,
                            },
                            purchase.id,
                        ),
                    ),
                )
            )

    if purchases:
        window_days = int(config.get("delay_window_days", 90))
        anchor = max(item.purchase_date for item in purchases)
        start = anchor - timedelta(days=window_days)
        for supplier_id, group in suppliers.items():
            completed = [
                item
                for item in group
                if item.purchase_date >= start
                and item.expected_delivery_date is not None
                and item.actual_delivery_date is not None
                and item.expected_delivery_date >= item.purchase_date
                and item.actual_delivery_date >= item.purchase_date
            ]
            late = [
                item
                for item in completed
                if item.actual_delivery_date is not None
                and item.expected_delivery_date is not None
                and item.actual_delivery_date > item.expected_delivery_date
            ]
            late_ids = {item.id for item in late}
            if len(completed) >= 3 and len(late) * 2 >= len(completed):
                findings.append(
                    FindingDraft(
                        "RECURRING_DELAY",
                        str(supplier_id),
                        "Fornecedor apresenta atraso recorrente nas entregas concluídas.",
                        tuple(
                            EvidenceDraft(
                                {
                                    "late": item.id in late_ids,
                                    "late_count": len(late),
                                    "completed_count": len(completed),
                                    "period_start": start.isoformat(),
                                    "period_end": anchor.isoformat(),
                                },
                                item.id,
                            )
                            for item in completed
                        ),
                    )
                )

    for row in rejected_rows:
        quantity_column = (column_mappings or {}).get(row.batch_id, {}).get("quantity", "quantity")
        quantity_errors = [
            error
            for error in row.errors
            if error.get("field") == "quantity" and error.get("code") == "non_positive"
        ]
        if quantity_errors:
            findings.append(
                FindingDraft(
                    "INVALID_QUANTITY",
                    str(row.id),
                    "Quantidade não positiva na linha de origem.",
                    (
                        EvidenceDraft(
                            {
                                "row_number": row.row_number,
                                "raw_quantity": row.raw_json.get(quantity_column),
                            },
                            import_row_id=row.id,
                        ),
                    ),
                )
            )
        findings.append(
            FindingDraft(
                "INCOMPLETE_RECORD",
                str(row.id),
                "Linha não analisável como compra.",
                (
                    EvidenceDraft(
                        {"row_number": row.row_number, "errors": row.errors}, import_row_id=row.id
                    ),
                ),
            )
        )
    limitation = (
        f"Preço inconclusivo para {insufficient} compras sem {PRICE_MIN_PEERS} pares comparáveis."
        if insufficient
        else None
    )
    return findings, limitation
