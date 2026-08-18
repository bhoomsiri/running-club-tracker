import type { ShirtSize } from "@/lib/types";

/**
 * The finisher shirt sizes, and the measurements that tell someone which one to pick.
 *
 * The same nine values the backend's `ShirtSize` accepts — anything else is a 422, which
 * is the point: the club prints one run of shirts and cannot re-order for a typo. If a
 * size is ever added, it is added in both places or it is not added at all.
 *
 * Measurements are the printer's, in inches, because that is how they are quoted on the
 * garment. Chest is measured flat and doubled ("รอบอก"), which is why 5XL is 50" and not
 * something a member would guess from their own tape measure — hence the table.
 */

export const SHIRT_SIZES: readonly ShirtSize[] = [
  "XS",
  "S",
  "M",
  "L",
  "XL",
  "2XL",
  "3XL",
  "4XL",
  "5XL",
];

export type ShirtMeasurement = {
  size: ShirtSize;
  /** รอบอก, นิ้ว */
  chestInches: number;
  /** ความยาว, นิ้ว */
  lengthInches: number;
};

export const SHIRT_SIZE_CHART: readonly ShirtMeasurement[] = [
  { size: "XS", chestInches: 34, lengthInches: 25 },
  { size: "S", chestInches: 36, lengthInches: 26 },
  { size: "M", chestInches: 38, lengthInches: 27 },
  { size: "L", chestInches: 40, lengthInches: 28 },
  { size: "XL", chestInches: 42, lengthInches: 29 },
  { size: "2XL", chestInches: 44, lengthInches: 30 },
  { size: "3XL", chestInches: 46, lengthInches: 31 },
  { size: "4XL", chestInches: 48, lengthInches: 31 },
  { size: "5XL", chestInches: 50, lengthInches: 31 },
];
