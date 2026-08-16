"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Card, EmptyState } from "@/components/ui";
import { ZoomableImage } from "@/components/zoomable-image";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDate, formatDecimal } from "@/lib/format";
import { fromDurationSeconds } from "@/lib/run-form";
import type { ReviewDecision, Run, RunWithEvidence } from "@/lib/types";

/**
 * The runs a member has submitted, with the evidence, and the decision buttons.
 *
 * Evidence URLs are presigned and short-lived — they come with this page's data and are
 * not stored anywhere, so a link copied out of the page stops working shortly after.
 *
 * A decision is never destructive: rejecting a run keeps the row and reverses the points
 * it earned, so a mistake here is corrected by deciding again rather than by digging
 * anything back out.
 */

const STATUS: Record<Run["review_status"], { label: string; tone: "neutral" | "success" }> = {
  ok: { label: "ผ่าน", tone: "success" },
  flagged: { label: "รอตรวจ", tone: "neutral" },
  rejected: { label: "ไม่ผ่าน", tone: "neutral" },
};

const DECISIONS: { value: ReviewDecision; label: string }[] = [
  { value: "ok", label: "ผ่าน" },
  { value: "flagged", label: "พักไว้" },
  { value: "rejected", label: "ไม่ผ่าน" },
];

export function RunReviewList({ runs }: { runs: RunWithEvidence[] }) {
  if (runs.length === 0) {
    return <EmptyState>สมาชิกยังไม่ได้ส่งผลวิ่ง</EmptyState>;
  }

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
  const api = useApi();
  const router = useRouter();
  const [busy, setBusy] = useState<ReviewDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState(entry.run.review_status);

  const { minutes, seconds } = fromDurationSeconds(entry.run.duration_seconds);

  async function decide(decision: ReviewDecision) {
    setError(null);
    setBusy(decision);
    try {
      const updated = await api<Run>(`/admin/runs/${entry.run.id}/review`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      setStatus(updated.review_status);
      // The decision reverses or restores points, so the totals above are now stale.
      router.refresh();
    } catch (decideError) {
      setError(messageFor(decideError));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <div className="flex flex-col gap-4 sm:flex-row">
        {/* Tappable, because deciding whether a run counts means reading the numbers on
            somebody's phone screenshot — and a 176px thumbnail is not where that
            happens. object-contain rather than cover for the same reason: a cropped
            screenshot is a screenshot with the distance cut off it. */}
        <ZoomableImage
          src={entry.evidence_url}
          alt={`หลักฐานการวิ่งวันที่ ${entry.run.run_date}`}
          className="h-48 w-full rounded-lg object-contain sm:h-32 sm:w-44"
        />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold tabular-nums">
              {formatDecimal(entry.run.distance_km)} กม.
            </span>
            <span className="text-sm text-muted tabular-nums">
              {minutes}:{seconds} นาที
            </span>
            <Badge tone={STATUS[status].tone}>{STATUS[status].label}</Badge>
          </div>

          <p className="mt-1 text-sm text-muted">
            วิ่งวันที่ {formatDate(entry.run.run_date)} · ส่งเมื่อ{" "}
            {formatDate(entry.run.created_at)} ·{" "}
            {entry.run.source === "app_screenshot" ? "แคปจากแอป" : "ถ่ายเอง"}
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {DECISIONS.map((decision) => (
              <button
                key={decision.value}
                type="button"
                onClick={() => void decide(decision.value)}
                disabled={busy !== null || status === decision.value}
                className={`min-h-12 rounded-control px-4 text-base disabled:opacity-40 ${
                  status === decision.value
                    ? "bg-brand font-semibold text-on-brand"
                    : "border border-border"
                }`}
              >
                {busy === decision.value ? "กำลังบันทึก…" : decision.label}
              </button>
            ))}
          </div>

          {error ? (
            <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
