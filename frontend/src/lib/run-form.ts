/**
 * Turning what a member types into what the backend expects, and back.
 *
 * `distance_km` never becomes a JavaScript number anywhere in here. The field is a
 * Decimal on the backend so a distance is stored exactly as submitted; parsing it to a
 * float to "validate" it and re-serialising would be enough to change it. So the string
 * is checked with a pattern and sent on as a string.
 */

/** Up to two decimals, which is what the backend's distance column stores. */
const DISTANCE_PATTERN = /^\d{1,3}(\.\d{1,2})?$/;

export function isValidDistance(value: string): boolean {
  const trimmed = value.trim();
  // "greater than zero" as a digit test rather than Number(trimmed) > 0, so this file
  // keeps its promise: the distance is never converted, not even to be checked.
  return DISTANCE_PATTERN.test(trimmed) && /[1-9]/.test(trimmed);
}

/** Seconds from the minutes/seconds the form collects. Both are whole numbers, so this
 * is integer arithmetic — no rounding to lose. */
export function toDurationSeconds(minutes: string, seconds: string): number | null {
  if (!/^\d{1,4}$/.test(minutes.trim()) || !/^\d{1,2}$/.test(seconds.trim())) return null;
  const total = Number(minutes) * 60 + Number(seconds);
  if (Number(seconds) > 59 || total <= 0) return null;
  return total;
}

export function fromDurationSeconds(total: number): { minutes: string; seconds: string } {
  return {
    minutes: String(Math.floor(total / 60)),
    seconds: String(total % 60).padStart(2, "0"),
  };
}

/** Today in the member's own timezone. `toISOString()` would use UTC and hand someone
 * running late at night in Bangkok yesterday's date. */
export function todayLocal(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
