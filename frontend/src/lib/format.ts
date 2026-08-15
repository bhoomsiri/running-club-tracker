/**
 * Display helpers for the decimal values the backend sends as strings.
 *
 * These deliberately never touch Number(). The backend keeps distance, points and costs
 * as Decimal so nothing is rounded on the way to the ledger, and turning them into
 * JavaScript floats here would put that rounding back at the last step — showing a
 * member a total the ledger does not agree with. So the string is manipulated as a
 * string: group the digits, trim meaningless zeros, and leave the value itself alone.
 */

/** "1234.5000" → "1,234.5" · "100.00" → "100" · "0" → "0" */
export function formatDecimal(value: string): string {
  const [whole, fraction] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const trimmed = fraction?.replace(/0+$/, "");
  return trimmed ? `${grouped}.${trimmed}` : grouped;
}

/**
 * The width of a progress bar, which is the one place a float is harmless: it lands in
 * a CSS percentage, not in anything anyone is owed. Clamped, because a member who runs
 * 130 km of a 100 km target should see a full bar rather than one that overflows.
 */
export function barWidth(percent: string | null): number {
  if (percent === null) return 0;
  const parsed = Number(percent);
  if (!Number.isFinite(parsed)) return 0;
  return Math.min(100, Math.max(0, parsed));
}

const UNIT_LABELS: Record<string, string> = {
  km: "กม.",
  points: "แต้ม",
  days: "วัน",
};

export function unitLabel(unit: string): string {
  return UNIT_LABELS[unit] ?? unit;
}

const DATE_FORMAT = new Intl.DateTimeFormat("th-TH", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** An ISO date or timestamp from the backend, in Thai. */
export function formatDate(iso: string): string {
  return DATE_FORMAT.format(new Date(iso));
}
