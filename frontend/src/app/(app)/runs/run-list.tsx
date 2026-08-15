"use client";

import { useEffect, useState } from "react";

import { Badge, Card } from "@/components/ui";
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
 */

const STATUS: Record<
  ReviewStatus,
  { icon: string; label: string; meaning: string; tone: "neutral" | "success" }
> = {
  ok: {
    icon: "✅",
    label: "ผ่าน",
    meaning: "นับระยะและแต้มเรียบร้อยแล้ว",
    tone: "success",
  },
  flagged: {
    icon: "🟡",
    label: "รอตรวจสอบ",
    meaning:
      "ผู้ดูแลกำลังตรวจ — ระหว่างนี้ยังนับความคืบหน้าให้ตามปกติ ถ้าตรวจแล้วไม่ผ่านจึงจะถูกหักออก",
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
  const [zoomed, setZoomed] = useState<RunWithEvidence | null>(null);

  return (
    <>
      <ul className="space-y-3">
        {runs.map((entry) => (
          <li key={entry.run.id}>
            <RunCard entry={entry} onZoom={() => setZoomed(entry)} />
          </li>
        ))}
      </ul>

      {zoomed ? (
        <Lightbox entry={zoomed} onClose={() => setZoomed(null)} />
      ) : null}
    </>
  );
}

function RunCard({
  entry,
  onZoom,
}: {
  entry: RunWithEvidence;
  onZoom: () => void;
}) {
  const status = STATUS[entry.run.review_status];
  const { minutes, seconds } = fromDurationSeconds(entry.run.duration_seconds);
  const rejected = entry.run.review_status === "rejected";

  return (
    <Card className={rejected ? "opacity-80" : ""}>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onZoom}
          aria-label="ดูรูปหลักฐานขนาดใหญ่"
          className="shrink-0"
        >
          {/* Plain <img>: the URL is presigned on a host that changes with the
              environment, and it expires in minutes — nothing for an image cache to
              key on. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={entry.evidence_url}
            alt={`หลักฐานการวิ่งวันที่ ${entry.run.run_date}`}
            className="h-20 w-20 rounded-lg bg-border object-cover"
          />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold tabular-nums">
              {formatDecimal(entry.run.distance_km)} กม.
            </span>
            <Badge tone={status.tone}>
              {status.icon} {status.label}
            </Badge>
          </div>

          <p className="mt-0.5 text-sm text-muted tabular-nums">
            {formatDate(entry.run.run_date)} · {minutes}:{seconds} นาที ·{" "}
            {entry.run.source === "app_screenshot" ? "แคปจากแอป" : "ถ่ายเอง"}
          </p>

          <p
            className={`mt-2 text-xs ${
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

function Lightbox({
  entry,
  onClose,
}: {
  entry: RunWithEvidence;
  onClose: () => void;
}) {
  // Escape closes it, and the page behind stops scrolling while it is open.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`หลักฐานการวิ่งวันที่ ${entry.run.run_date}`}
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={entry.evidence_url}
        alt={`หลักฐานการวิ่งวันที่ ${entry.run.run_date}`}
        className="max-h-full max-w-full rounded-lg object-contain"
      />
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 rounded-full bg-white/90 px-4 py-2 text-sm font-medium text-black"
      >
        ปิด
      </button>
    </div>
  );
}
