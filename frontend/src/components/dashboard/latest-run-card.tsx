import { formatCount, formatDecimal, formatPace, formatShortDate } from "@/lib/format";
import type { LatestRun } from "@/lib/types";

/**
 * The member's most recent run, by the day they ran rather than the day they submitted
 * it — so someone catching up on last week's runs does not see the oldest of them here.
 *
 * Calories and steps show a dash when the screenshot did not carry them, never a zero.
 * Most running apps print one and not the other, so absent is the ordinary case and has
 * to look different from "you burned none" (golden rule #4).
 */
export function LatestRunCard({ run }: { run: LatestRun }) {
  return (
    <section className="card">
      <div className="flex items-start justify-between gap-2">
        <span className="inline-flex items-center rounded-full border border-border bg-background px-2.5 py-1 text-xs font-semibold text-muted">
          ล่าสุด · {formatShortDate(run.run_date)}
        </span>
        <span
          aria-hidden
          className="grid size-10 shrink-0 place-items-center rounded-control bg-brand-tint text-brand"
        >
          🏃
        </span>
      </div>

      <p className="mt-3 font-semibold">การวิ่งครั้งล่าสุด</p>

      <dl className="mt-3 grid grid-cols-2 gap-x-2 gap-y-3">
        <Field label="ระยะ" value={`${formatDecimal(run.distance_km)} กม.`} />
        <Field label="Pace" value={formatPace(run.pace_min_per_km) ?? "—"} />
        <Field
          label="แคลอรี่"
          value={run.calories_burned === null ? null : formatCount(run.calories_burned)}
        />
        <Field label="ก้าว" value={run.steps === null ? null : formatCount(run.steps)} />
      </dl>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-muted">{label}</dt>
      {value === null ? (
        <dd className="text-base text-muted">ไม่ได้บันทึก</dd>
      ) : (
        <dd className="text-lg font-bold tabular-nums">{value}</dd>
      )}
    </div>
  );
}
