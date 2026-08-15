import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import type { RunWithEvidence } from "@/lib/types";

import { RunList } from "./run-list";

/**
 * Everything this member has submitted, newest first.
 *
 * It exists mainly for one case: a run that was turned down. Progress is reconciled
 * against what counts, so a rejection takes its distance and points back — and until
 * now the member would have seen their totals drop with nothing on any screen to say
 * why. Evidence URLs are presigned and short-lived; they arrive with this page and are
 * not stored anywhere.
 */
export default async function MyRunsPage() {
  const runs = await apiServer<RunWithEvidence[]>("/me/runs");

  // Counts only. Adding the distances up here would mean parsing each one to a float —
  // the rounding the whole app avoids — and would put a second total on screen that
  // could disagree with the dashboard's by a hair. The backend owns that number.
  const counted = runs.filter((entry) => entry.run.review_status !== "rejected");
  const rejected = runs.length - counted.length;

  return (
    <>
      <PageHeader
        title="ผลวิ่งของฉัน"
        subtitle="ทุกครั้งที่ส่ง พร้อมสถานะการตรวจสอบ"
      />

      {runs.length === 0 ? (
        <EmptyState>
          ยังไม่ได้ส่งผลวิ่ง —{" "}
          <Link href="/submit" className="text-brand underline">
            ส่งผลวิ่งครั้งแรก
          </Link>
        </EmptyState>
      ) : (
        <>
          <p className="mb-4 text-sm text-muted tabular-nums">
            ส่งแล้ว {runs.length} ครั้ง · นับ {counted.length} ครั้ง
            {rejected > 0 ? ` · ไม่ผ่าน ${rejected} ครั้ง` : ""} ·{" "}
            <Link href="/dashboard" className="underline">
              ดูระยะสะสมรวม
            </Link>
          </p>

          {rejected > 0 ? (
            <p className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
              มีผลวิ่งที่ไม่ผ่านการตรวจสอบ {rejected} ครั้ง — ระยะและแต้มจากรายการเหล่านั้นถูกหักออกแล้ว
              จึงเป็นเหตุผลที่ตัวเลขในแดชบอร์ดอาจน้อยกว่าที่คุณคิด
            </p>
          ) : null}

          <RunList runs={runs} />
        </>
      )}
    </>
  );
}
