export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function displayNumber(value: unknown, digits = 2): string {
  const number = asNumber(value);
  return number === null ? "—" : number.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function displayCurrency(value: unknown, currency = "USD"): string {
  const number = asNumber(value);
  return number === null
    ? "—"
    : new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(number);
}

export function displayPercent(value: unknown, digits = 1): string {
  const number = asNumber(value);
  return number === null ? "—" : `${number.toFixed(digits)}%`;
}

export function dateLabels(rows: Record<string, unknown>[], key = "date"): string[] {
  return rows.map((row) => String(row[key] ?? ""));
}
