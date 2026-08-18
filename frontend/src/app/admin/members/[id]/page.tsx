import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge, Card } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { barWidth, formatDecimal, unitLabel } from "@/lib/format";
import { isStaff, isSuperuser, ROLE_LABELS } from "@/lib/roles";
import type { MemberProgress, MemberSummary, RunWithEvidence } from "@/lib/types";

import { RoleToggle } from "./role-toggle";
import { RunReviewList } from "./run-review";
import { SensitivePanel } from "./sensitive-panel";

/**
 * One member, seen by the club's staff.
 *
 * Only the non-sensitive half loads with the page: standing, campaign progress and the
 * runs with their evidence. Health, screening and contact details each sit behind their
 * own button, because fetching them writes an audit row — loading them here would mean
 * three rows every time anyone opened anyone's page, and an audit log full of glances is
 * one nobody reads.
 *
 * Admins and the superuser see the same page. The one difference is the role control at
 * the bottom, which decides who else may reach any of this and so belongs to the one
 * person answerable for it.
 */
export default async function AdminMemberPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const summary = await apiServer<MemberSummary>("/me/summary");
  if (!isStaff(summary.member.role)) {
    redirect("/dashboard");
  }

  const [progress, runs] = await Promise.all([
    apiServer<MemberProgress>(`/admin/members/${id}/summary`),
    apiServer<RunWithEvidence[]>(`/admin/members/${id}/runs`),
  ]);

  return (
    <>
      <Link href="/admin" className="text-base text-muted underline">
        ‹ กลับไปภาพรวม
      </Link>

      <header className="mt-4 mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">
            {progress.member.name}
          </h1>
          {progress.member.role !== "member" ? (
            <Badge tone="brand">{ROLE_LABELS[progress.member.role]}</Badge>
          ) : null}
          {progress.pending_review_count > 0 ? (
            <Badge>รอตรวจ {progress.pending_review_count}</Badge>
          ) : null}
        </div>
        {progress.member.department ? (
          <p className="mt-2 text-base">
            {progress.member.position ? `${progress.member.position} · ` : ""}
            {progress.member.department}
          </p>
        ) : null}
        <p className="mt-2 text-base text-muted tabular-nums">
          ระยะสะสม {formatDecimal(progress.total_distance_km)} กม. · ส่งแล้ว{" "}
          {progress.run_count} ครั้ง
        </p>
      </header>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">ความคืบหน้ากิจกรรม</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {progress.campaigns.map((campaign) => (
            <Card key={campaign.campaign_id}>
              <div className="flex items-start justify-between gap-2">
                <p className="text-lg font-semibold">{campaign.name}</p>
                {campaign.completed ? <Badge tone="success">สำเร็จแล้ว</Badge> : null}
              </div>
              <p className="mt-2 tabular-nums">
                <span className="text-xl font-semibold">
                  {formatDecimal(campaign.value)}
                </span>
                {campaign.target !== null ? (
                  <span className="text-muted"> / {formatDecimal(campaign.target)}</span>
                ) : null}
                <span className="ml-1 text-sm text-muted">
                  {unitLabel(campaign.unit)}
                </span>
              </p>
              {campaign.percent !== null ? (
                <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border">
                  <div
                    className="h-full rounded-full bg-brand"
                    style={{ width: `${barWidth(campaign.percent)}%` }}
                  />
                </div>
              ) : null}
              {campaign.points_balance !== null ? (
                <p className="mt-2 text-sm tabular-nums">
                  แต้มคงเหลือ {formatDecimal(campaign.points_balance)} แต้ม
                </p>
              ) : null}
            </Card>
          ))}
        </div>
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">
          ผลวิ่งและการตรวจสอบ ({runs.length})
        </h2>
        <RunReviewList runs={runs} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">ข้อมูลอ่อนไหว</h2>
        <SensitivePanel memberId={id} />
      </section>

      {isSuperuser(summary.member.role) ? (
        <section className="mt-8">
          <h2 className="mb-3 text-lg font-semibold">สิทธิ์การใช้งาน</h2>
          <RoleToggle member={progress.member} />
        </section>
      ) : null}
    </>
  );
}
