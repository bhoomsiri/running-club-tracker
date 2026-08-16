"use client";

import { Badge, Card } from "@/components/ui";
import { ZoomableImage } from "@/components/zoomable-image";
import { formatDate, formatDecimal } from "@/lib/format";
import { fromDurationSeconds } from "@/lib/run-form";
import type { ReviewStatus, RunWithEvidence } from "@/lib/types";

/**
 * A member's own submissions.
 *
 * The reason this screen exists is the rejected case. Points and distance are
 * reconciled against what counts, so a run that is turned down takes its contribution
 * back — and without this list the member would see their total drop with no
 * explanation at all. So the status is spelled out in words rather than shown as a
 * colour, and a rejected run says what to do about it.
 *
 * Submitting counts straight away: nothing waits for approval, and the wording says so
 * rather than leaving people watching for a review that is not coming. "รอตรวจสอบ" is
 * the exception, not the default — a run only lands there when an admin sets it aside.
 */

const STATUS: Record<
  ReviewStatus,
  { icon: string; label: string; meaning: string; tone: "neutral" | "success" }
> = {
  ok: {
    icon: "✅",
    label: "ผ่าน",
    meaning: "นับระยะและแต้มให้ทันทีที่ส่ง ไม่ต้องรออนุมัติ",
    tone: "success",
  },
  flagged: {
    icon: "🟡",
    label: "รอตรวจสอบ",
    meaning:
      "ผู้ดูแลยกรายการนี้ไว้ตรวจเพิ่ม — ระหว่างนี้ยังนับความคืบหน้าให้ตามปกติ ถ้าตรวจแล้วไม่ผ่านจึงจะถูกหักออก",
    tone: "neutral",
  },
  rejected: {
    icon: "❌",
    label: "ไม่ผ่าน",
    meaning:
      "ไม่ถูกนับทั้งระยะและแต้ม — ถ้าคุณเห็นตัวเลขลดลง มาจากรายการนี้ หากสงสัยกรุณาติดต่อผู้ดูแลชมรม",
    tone: "neutral",
  },
};

export function RunList({ runs }: { runs: RunWithEvidence[] }) {
  return (
    <ul className="space-y-3">
      {runs.map((entry) => (
        <li key={entry.run.id}>
          <RunCard entry={entry} />
        </li>
      ))}
    </ul>
  );
}

function RunCard({ entry }: { entry: RunWithEvidence }) {
  const status = STATUS[entry.run.review_status];
  const { minutes, seconds } = fromDurationSeconds(entry.run.duration_seconds);
  const rejected = entry.run.review_status === "rejected";

  return (
    <Card className={rejected ? "opacity-80" : ""}>
      <div className="flex gap-3">
        <ZoomableImage
          src={entry.evidence_url}
          alt={`หลักฐานการวิ่งวันที่ ${entry.run.run_date}`}
          className="h-20 w-20 rounded-lg object-cover"
        />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold tabular-nums">
              {formatDecimal(entry.run.distance_km)} กม.
            </span>
            <Badge tone={status.tone}>
              {status.icon} {status.label}
            </Badge>
          </div>

          <p className="mt-1 text-base text-muted tabular-nums">
            {formatDate(entry.run.run_date)} · {minutes}:{seconds} นาที ·{" "}
            {entry.run.source === "app_screenshot" ? "แคปจากแอป" : "ถ่ายเอง"}
          </p>

          <p
            className={`mt-2 text-sm ${
              rejected
                ? "text-red-700 dark:text-red-300"
                : entry.run.review_status === "flagged"
                  ? "text-amber-700 dark:text-amber-300"
                  : "text-muted"
            }`}
          >
            {status.meaning}
          </p>
        </div>
      </div>
    </Card>
  );
}
