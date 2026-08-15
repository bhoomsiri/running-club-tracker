import { BMI_BANDS, bandFor, shouldSeeADoctor } from "@/lib/bmi";
import { formatDecimal } from "@/lib/format";

/**
 * The BMI reading with the band table underneath, the member's own row highlighted.
 *
 * The whole table is shown rather than only the band they landed in: a number on its own
 * says nothing, and seeing where it sits — and how far the next boundary is — is the
 * point of measuring before and after at all.
 */
export function BmiScale({ bmi, caption }: { bmi: string; caption?: string }) {
  const band = bandFor(bmi);

  return (
    <div>
      <p className="flex items-baseline gap-2">
        <span className="text-sm text-muted">{caption ?? "BMI"}</span>
        <span className="text-2xl font-semibold tabular-nums">{formatDecimal(bmi)}</span>
        {band ? <span className="text-sm text-muted">{band.label}</span> : null}
      </p>

      <ul className="mt-3 space-y-1">
        {BMI_BANDS.map((row) => {
          const mine = row.id === band?.id;
          return (
            <li
              key={row.id}
              aria-current={mine ? "true" : undefined}
              className={`flex items-center gap-2.5 rounded-lg border px-2.5 py-1.5 text-sm ${
                mine ? row.highlight : "border-transparent"
              }`}
            >
              <span aria-hidden className={`h-3 w-3 shrink-0 rounded-sm ${row.swatch}`} />
              <span className="w-24 shrink-0 tabular-nums text-muted">{row.range}</span>
              <span className={mine ? "font-semibold" : "text-muted"}>{row.label}</span>
              {mine ? (
                <span className="ml-auto text-xs font-medium">← คุณอยู่ตรงนี้</span>
              ) : null}
            </li>
          );
        })}
      </ul>

      {band && shouldSeeADoctor(band) ? (
        <p className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
          ค่า BMI ของคุณสูงกว่าเกณฑ์ปกติ แนะนำให้พบแพทย์เพื่อตรวจเพิ่มเติมและวางแผนดูแลสุขภาพ
          — ค่านี้เป็นเพียงการคัดกรองเบื้องต้น ไม่ใช่การวินิจฉัย
        </p>
      ) : null}

      <p className="mt-2 text-xs text-muted">
        ใช้เกณฑ์สำหรับชาวเอเชีย ซึ่งกำหนดจุดตัดต่ำกว่าเกณฑ์สากล (23 แทน 25)
      </p>
    </div>
  );
}
