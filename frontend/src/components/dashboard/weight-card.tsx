import Link from "next/link";

import { bandFor } from "@/lib/bmi";
import { formatDecimal } from "@/lib/format";
import type { HealthComparison } from "@/lib/types";

/**
 * Weight and BMI, from the screening measurements the member already gave.
 *
 * Nothing new is collected and nothing is stored: BMI is derived at read time by the
 * domain, as it always has been. This card is the same data, laid out to be read.
 *
 * **The band, never the advice.** `bandFor` gives the Thai/Asian cut-offs and this shows
 * that label; `shouldSeeADoctor` is deliberately not called here. "แนะนำให้พบแพทย์" stays
 * on /health, a screen someone chose to open — a dashboard that greets a member with a
 * medical suggestion every time they check their distance is diagnostic, not
 * informational, and this is a hospital's club, which makes the difference matter more.
 *
 * **Two points, not a series.** There is a before and an after and nothing between them,
 * so it shows the latest value and the change from the start rather than pretending to a
 * trend. Before only means no delta — a change from one measurement is not a change.
 *
 * The member sees their own measurements whether or not their consent is still active:
 * consent governs what the club may do with the data, not whether the person it
 * describes may look at it (PDPA มาตรา 30). The gate that makes withdrawal mean
 * something is on the admin's side, and on the export.
 */
export function WeightCard({ comparison }: { comparison: HealthComparison }) {
  const latest = comparison.after ?? comparison.before;
  const weight = latest?.weight_kg ?? null;
  const startWeight = comparison.before?.weight_kg ?? null;
  const bmi = comparison.bmi_after ?? comparison.bmi_before;
  const band = bmi ? bandFor(bmi) : null;

  return (
    <section className="card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">⚖️ น้ำหนัก และ BMI</h3>
          <p className="text-xs text-muted">จากการวัดในโปรแกรมคัดกรอง</p>
        </div>
        {bmi && band ? (
          <span
            className={`shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold ${band.highlight}`}
          >
            BMI {formatDecimal(bmi)} · {band.label}
          </span>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          {weight === null ? (
            <p className="text-base text-muted">ยังไม่ได้บันทึกน้ำหนัก</p>
          ) : (
            <>
              <p className="flex items-end gap-2">
                <b className="text-3xl font-bold tabular-nums">{formatDecimal(weight)}</b>
                <span className="mb-1 font-semibold text-muted">กก. ปัจจุบัน</span>
              </p>
              <WeightChange start={startWeight} latest={weight} />
            </>
          )}
        </div>

        <div className="sm:border-l sm:border-border sm:pl-4">
          <p className="text-xs text-muted">ค่าดัชนีมวลกาย (BMI)</p>
          {bmi === null ? (
            <p className="mt-1 text-base text-muted">
              คำนวณไม่ได้ — ยังไม่มีส่วนสูงหรือน้ำหนัก
            </p>
          ) : (
            <>
              <p className="text-3xl font-bold tabular-nums">{formatDecimal(bmi)}</p>
              {comparison.bmi_delta !== null ? (
                <p className="mt-1 text-sm text-muted tabular-nums">
                  เปลี่ยนจากตอนเริ่ม {withSign(comparison.bmi_delta)}
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>

      <Link
        href="/health"
        className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand"
      >
        ดูรายละเอียดสุขภาพ ›
      </Link>
    </section>
  );
}

/** The change from the first measurement, or nothing when there is only one. */
function WeightChange({ start, latest }: { start: string | null; latest: string }) {
  if (start === null || start === latest) return null;
  return (
    <p className="mt-2 text-sm text-muted tabular-nums">
      เริ่มต้น {formatDecimal(start)} กก. → ตอนนี้ {formatDecimal(latest)} กก.
    </p>
  );
}

/** The backend sends "-0.8" already signed; a gain arrives as "0.8" and needs the plus
 * to read as a direction rather than a value. */
function withSign(delta: string): string {
  return delta.startsWith("-") ? delta : `+${delta}`;
}
