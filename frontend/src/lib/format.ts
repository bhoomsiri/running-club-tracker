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

/** Whole counts the backend sends as numbers — calories, steps, members. */
export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/**
 * "5.800" → "5:48". A pace is minutes-and-seconds to every runner alive, and 5.8 นาที/กม.
 * is a number they would have to convert in their head.
 *
 * Done on the digits rather than through Number(): the fraction is a known number of
 * decimal places, so `800/1000 × 60` is integer arithmetic that cannot drift. Same
 * reason `formatDecimal` above never parses either.
 */
export function formatPace(value: string | null): string | null {
  if (value === null) return null;
  const [whole, fraction = ""] = value.split(".");
  const minutes = Number(whole);
  if (!Number.isInteger(minutes) || minutes < 0) return null;
  const scale = 10 ** fraction.length;
  const seconds = fraction === "" ? 0 : Math.round((Number(fraction) * 60) / scale);
  // 5.999 rounds to 60 seconds, which is 6:00 and not 5:60.
  const [m, s] = seconds === 60 ? [minutes + 1, 0] : [minutes, seconds];
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 22320 → { hours: 6, minutes: 12 }. Seconds are dropped: nobody reads their weekly
 * running time to the second, and "6 ชม. 12 น. 3 วิ." is harder to take in. */
export function splitDuration(totalSeconds: number): { hours: number; minutes: number } {
  return {
    hours: Math.floor(totalSeconds / 3600),
    minutes: Math.floor((totalSeconds % 3600) / 60),
  };
}

const DAY_FORMAT = new Intl.DateTimeFormat("th-TH", { weekday: "narrow" });

/** The one-character weekday under a bar: จ อ พ พฤ ศ ส อา. */
export function weekdayLetter(iso: string): string {
  return DAY_FORMAT.format(new Date(`${iso}T00:00:00`));
}

const SHORT_DATE_FORMAT = new Intl.DateTimeFormat("th-TH", {
  day: "numeric",
  month: "short",
});

/** "27 ส.ค." — for labels where the year is obvious from context. */
export function formatShortDate(iso: string): string {
  return SHORT_DATE_FORMAT.format(new Date(iso));
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
