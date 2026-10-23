const MONEY_FIELDS = new Set([
  "declared_total", "calculated_total", "difference", "unit_price", "limit",
  "median", "q1", "q3", "mad", "margin",
]);

function currencyDecimals(currency: unknown): number {
  if (typeof currency !== "string") return 2;
  try {
    return new Intl.NumberFormat("en", { style: "currency", currency })
      .resolvedOptions().minimumFractionDigits ?? 2;
  } catch {
    return 2;
  }
}

// Remove apenas zeros redundantes; mantém qualquer precisão não nula da evidência original.
export function trimMoneyZeros(value: string, minimumDecimals = 2): string {
  if (!/^-?\d+\.\d+$/.test(value)) return value;
  const [integer, fraction] = value.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  const visible = trimmed.padEnd(Math.min(minimumDecimals, fraction.length), "0");
  return visible ? `${integer}.${visible}` : integer;
}

export function displayEvidence(data: Record<string, unknown>): string {
  return JSON.stringify(data, function (this: Record<string, unknown>, key, value: unknown) {
    return MONEY_FIELDS.has(key) && typeof value === "string"
      ? trimMoneyZeros(value, currencyDecimals(this.currency)) : value;
  }, 2);
}

// Textos da IA já salvos são apresentados com a mesma precisão monetária das evidências.
export function displayAiMoney(text: string): string {
  return text.replace(/\b(\d+\.\d{3,})\s+([A-Z]{3})\b/g, (_, amount: string, currency: string) =>
    `${trimMoneyZeros(amount, currencyDecimals(currency))} ${currency}`);
}
