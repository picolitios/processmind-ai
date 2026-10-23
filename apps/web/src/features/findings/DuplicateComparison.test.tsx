import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { Evidence } from "../../lib/api";
import { DuplicateComparison } from "./DuplicateComparison";

const common = {
  supplier_id: "FORN-ALFA",
  product_id: "SKU-CABO",
  product_name: "Cabo",
  purchase_date: "2026-09-03",
  quantity: "10.0000",
  unit_of_measure: "un",
  unit_price: "12.5000",
  declared_total: "125.00",
  currency: "BRL",
  import_id: "same-import",
};

test("explica que IDs diferentes com campos iguais são apenas possível duplicidade", () => {
  const evidence: Evidence[] = ["P-TEST-001", "P-TEST-002"].map((purchaseId) => ({
    id: purchaseId,
    type: "purchase",
    data: { purchase: { ...common, purchase_id: purchaseId } },
  }));
  render(<DuplicateComparison evidence={evidence} />);
  expect(screen.getByText(/Possível compra duplicada/)).toBeTruthy();
  expect(screen.getByText(/O produto é o mesmo/)).toBeTruthy();
  expect(screen.getByText(/mesma importação/)).toBeTruthy();
  expect(screen.getByText(/Ainda não é um erro confirmado/)).toBeTruthy();
  expect(screen.getAllByText("SKU-CABO")).toHaveLength(2);
});
