/**
 * BMI bands, Asian/Thai cut-offs.
 *
 * These are NOT the WHO international cut-offs most charts show. The overweight
 * threshold is 23, not 25, because the same BMI carries more metabolic risk in Asian
 * populations — using the international scale here would tell a member at 24 that they
 * are in the normal range when the guidance their doctor follows says otherwise.
 *
 * The labels name the ranges the way a printed chart does (18.5–22.9, 23–24.9 …), but
 * the code uses exclusive upper bounds instead, so every value lands in exactly one
 * band. Reading the printed labels literally would leave gaps — 22.95 sits between
 * "22.9" and "23" and would match nothing. Here it is below 23, so it is still ปกติ.
 */

export type BmiBand = {
  id: string;
  /** Exclusive upper bound; null for the last band. */
  below: number | null;
  range: string;
  label: string;
  /** Tailwind classes for the band's swatch and its highlighted row. */
  swatch: string;
  highlight: string;
};

export const BMI_BANDS: BmiBand[] = [
  {
    id: "underweight",
    below: 18.5,
    range: "น้อยกว่า 18.5",
    label: "น้ำหนักต่ำกว่าเกณฑ์",
    swatch: "bg-sky-400",
    highlight: "bg-sky-400/15 border-sky-400",
  },
  {
    id: "normal",
    below: 23,
    range: "18.5 – 22.9",
    label: "น้ำหนักตามเกณฑ์ (ปกติ)",
    swatch: "bg-emerald-500",
    highlight: "bg-emerald-500/15 border-emerald-500",
  },
  {
    id: "overweight",
    below: 25,
    range: "23 – 24.9",
    label: "น้ำหนักมากกว่าเกณฑ์ (ท้วม)",
    swatch: "bg-amber-400",
    highlight: "bg-amber-400/20 border-amber-400",
  },
  {
    id: "obese-1",
    below: 30,
    range: "25 – 29.9",
    label: "โรคอ้วนระดับ 1",
    swatch: "bg-orange-500",
    highlight: "bg-orange-500/15 border-orange-500",
  },
  {
    id: "obese-2",
    below: 40,
    range: "30 – 39.9",
    label: "โรคอ้วนระดับ 2",
    swatch: "bg-red-500",
    highlight: "bg-red-500/15 border-red-500",
  },
  {
    id: "obese-3",
    below: null,
    range: "40 ขึ้นไป",
    label: "โรคอ้วนระดับ 3",
    swatch: "bg-red-700",
    highlight: "bg-red-700/15 border-red-700",
  },
];

/** From 'overweight' onwards the advice is to have it looked at. */
const SEE_A_DOCTOR_FROM = 2;

/**
 * Which band a BMI falls in, or null if it cannot be read.
 *
 * This is the one place a BMI string becomes a number, and it is safe here for the same
 * reason the progress bar was: the result is a category to display, never a value that
 * is stored or compared against anything anyone is owed. The number the member sees is
 * still the string the backend sent.
 */
export function bandFor(bmi: string): BmiBand | null {
  const value = Number(bmi);
  if (!Number.isFinite(value)) return null;
  return BMI_BANDS.find((band) => band.below === null || value < band.below) ?? null;
}

export function shouldSeeADoctor(band: BmiBand): boolean {
  return BMI_BANDS.indexOf(band) >= SEE_A_DOCTOR_FROM;
}
