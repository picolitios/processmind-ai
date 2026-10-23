import { expect, test } from "vitest";
import { displayAiMoney, displayEvidence, trimMoneyZeros } from "./formatMoney";

test("mostra totais calculados com dois decimais sem mudar os dados", () => {
  const evidence = { currency: "BRL", declared_total: "100.00", calculated_total: "120.00000000", difference: "20.00000000", quantity: "1.00000000" };
  const original = structuredClone(evidence);
  expect(displayEvidence(evidence)).toContain('"difference": "20.00"');
  expect(displayEvidence(evidence)).toContain('"quantity": "1.00000000"');
  expect(evidence).toEqual(original);
});

test("preserva dígitos significativos e formata valores repetidos pela IA", () => {
  expect(trimMoneyZeros("20.12500000")).toBe("20.125");
  expect(displayAiMoney("Desvio de 20.00000000 BRL e 15.12000000 BRL."))
    .toBe("Desvio de 20.00 BRL e 15.12 BRL.");
  expect(displayAiMoney("Total de 100.00000000 JPY.")).toBe("Total de 100 JPY.");
});
