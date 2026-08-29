import { formatDecimal, weekdayLetter } from "@/lib/format";
import type { DayDistance } from "@/lib/types";

/**
 * Seven days of distance, as bars.
 *
 * A rest day draws a dashed stub rather than nothing, because zero km on Tuesday is a
 * fact the member can act on and an absent bar looks like a chart that failed to load.
 * That is the opposite of the calorie card, where zero would mean "no screenshot said" —
 * the backend keeps the two kinds of nothing apart and so does this.
 *
 * Heights are percentages of the best day in the window, not of some fixed ceiling: a
 * week of 2 km runs should look like a week of running, not like a flat line under a
 * 10 km scale nobody chose.
 *
 * The bar heights are the one place a Decimal becomes a float, and it is safe for the
 * same reason `barWidth` is — the result lands in a CSS percentage, never in a number
 * anyone is owed. Every value the member reads is still the string the backend sent.
 */
export function WeekChart({ days }: { days: DayDistance[] }) {
  const values = days.map((day) => Number(day.distance_km));
  const peak = Math.max(...values, 0);
  const total = values.reduce((sum, value) => sum + value, 0);
  const best = peak > 0 ? days[values.indexOf(peak)] : null;

  return (
    <section className="card">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">ระยะวิ่ง 7 วันล่าสุด</h3>
        <span className="inline-flex items-center rounded-full border border-border bg-background px-2.5 py-1 text-xs font-semibold text-muted tabular-nums">
          รวม {total.toFixed(1)} กม.
        </span>
      </div>

      <div className="mt-5 flex h-40 items-end gap-2 border-b border-border">
        {days.map((day, index) => (
          <Bar
            key={day.day}
            day={day}
            // A share of the tallest bar, floored so a very short run is still visible.
            percent={peak > 0 ? Math.max(3, (values[index] / peak) * 100) : 0}
            isPeak={peak > 0 && values[index] === peak}
          />
        ))}
      </div>

      <div className="mt-2 flex gap-2">
        {days.map((day) => (
          <p key={day.day} className="flex-1 text-center text-xs text-muted">
            {weekdayLetter(day.day)}
          </p>
        ))}
      </div>

      <p className="mt-3 flex items-baseline justify-between gap-3 text-xs text-muted">
        <span>ระยะต่อวัน (กม.)</span>
        {best ? (
          <span>
            สูงสุด{" "}
            <b className="text-foreground tabular-nums">
              {formatDecimal(best.distance_km)} กม.
            </b>
          </span>
        ) : (
          <span>ยังไม่ได้วิ่งในช่วง 7 วันนี้</span>
        )}
      </p>
    </section>
  );
}

function Bar({
  day,
  percent,
  isPeak,
}: {
  day: DayDistance;
  percent: number;
  isPeak: boolean;
}) {
  const kilometres = formatDecimal(day.distance_km);
  const label = percent > 0 ? `${day.day} · ${kilometres} กม.` : `${day.day} · พัก`;

  return (
    <div className="relative flex h-full flex-1 flex-col items-center justify-end">
      {isPeak ? (
        <span className="mb-1 text-xs font-bold tabular-nums">{kilometres}</span>
      ) : null}
      {percent > 0 ? (
        <span
          title={label}
          aria-label={label}
          className="w-[70%] max-w-9 rounded-t bg-brand"
          style={{ height: `${percent}%` }}
        />
      ) : (
        // A rest day, drawn as a stub so the day keeps its place in the week.
        <span
          title={label}
          aria-label={label}
          className="h-1 w-[70%] max-w-9 rounded-full bg-grid"
        />
      )}
    </div>
  );
}
