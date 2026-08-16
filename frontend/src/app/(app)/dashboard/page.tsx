import Link from "next/link";

import { AnnouncementBody } from "@/components/announcement-body";
import { Badge, Card, EmptyState, ProgressBar } from "@/components/ui";
import { apiPublic } from "@/lib/api";
import { apiServer } from "@/lib/api-server";
import { barWidth, formatDate, formatDecimal, unitLabel } from "@/lib/format";
import type {
  Announcement,
  CampaignProgress,
  MemberSummary,
  Redemption,
  Role,
} from "@/lib/types";

/**
 * Rendered on the server so the member's numbers arrive with the HTML rather than after
 * a second round trip on a phone connection. Nothing here is cached — the summary is
 * per-member and changes the moment a run is submitted.
 */

const ROLE_LABELS: Record<Role, string> = {
  member: "สมาชิก",
  admin: "ผู้ดูแล",
  superuser: "ผู้ดูแลระบบ",
};

const REDEMPTION_LABELS: Record<Redemption["status"], string> = {
  pending: "รอรับของ",
  fulfilled: "รับของแล้ว",
  cancelled: "ยกเลิก",
};

export default async function DashboardPage() {
  // The news is public and the summary is not, so they are fetched by different
  // clients — but they are fetched together, because two round trips in sequence is a
  // second of blank screen on a phone.
  const [summary, news] = await Promise.all([
    apiServer<MemberSummary>("/me/summary"),
    latestNews(),
  ]);

  return (
    <>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">
            สวัสดี {summary.member.name}
          </h1>
          {summary.member.role !== "member" ? (
            <Badge tone="brand">{ROLE_LABELS[summary.member.role]}</Badge>
          ) : null}
        </div>
        <p className="mt-1 text-sm text-muted">ความคืบหน้ากิจกรรมของคุณ</p>
      </header>

      {/* The only way into the admin screens, and only the superuser sees it. The page
          itself checks again, and the backend refuses regardless — this link is
          navigation, not access control. */}
      {summary.member.role === "superuser" ? (
        <Link
          href="/admin"
          className="mb-6 flex items-center justify-between rounded-xl border border-brand/40 bg-brand/5 px-4 py-3 text-sm"
        >
          <span className="font-medium text-brand">ภาพรวมสมาชิกทั้งชมรม</span>
          <span aria-hidden className="text-brand">
            ›
          </span>
        </Link>
      ) : null}

      {news ? (
        <Link href="/announcements" className="mb-6 block">
          <Card>
            <div className="flex items-start justify-between gap-3">
              <p className="text-xs font-medium text-brand">ข่าวจากชมรม</p>
              <span className="shrink-0 text-xs text-muted">ดูทั้งหมด ›</span>
            </div>
            <p className="mt-1 font-medium">{news.title}</p>
            <AnnouncementBody body={news.body} className="mt-1 line-clamp-2 text-sm" />
          </Card>
        </Link>
      ) : null}

      <Card className="mb-6 text-center">
        <p className="text-sm text-muted">ระยะสะสมรวม</p>
        <p className="mt-1 text-4xl font-semibold tabular-nums">
          {formatDecimal(summary.total_distance_km)}
          <span className="ml-1.5 text-base font-normal text-muted">กม.</span>
        </p>
      </Card>

      <h2 className="mb-3 text-sm font-semibold text-muted">กิจกรรม</h2>
      {summary.campaigns.length === 0 ? (
        <EmptyState>ยังไม่มีกิจกรรมที่เปิดอยู่</EmptyState>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {summary.campaigns.map((campaign) => (
            <li key={campaign.campaign_id}>
              <CampaignCard campaign={campaign} />
            </li>
          ))}
        </ul>
      )}

      <h2 className="mt-8 mb-3 text-sm font-semibold text-muted">ของรางวัลที่แลกแล้ว</h2>
      {summary.redemptions.length === 0 ? (
        <EmptyState>
          ยังไม่ได้แลกของรางวัล — สะสมแต้มจากกิจกรรมวันละ 10 กม. แล้วไปที่หน้ารางวัล
        </EmptyState>
      ) : (
        <ul className="grid gap-3">
          {summary.redemptions.map((redemption) => (
            <li key={redemption.id}>
              <Card className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium tabular-nums">
                    {formatDecimal(redemption.points_spent)} แต้ม
                  </p>
                  <p className="text-xs text-muted">
                    {formatDate(redemption.created_at)}
                  </p>
                </div>
                <Badge tone={redemption.status === "fulfilled" ? "success" : "neutral"}>
                  {REDEMPTION_LABELS[redemption.status]}
                </Badge>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** The latest notice, or nothing at all. A dashboard that fails to load because the
 * notice board is down would be a bad trade for a headline. */
async function latestNews(): Promise<Announcement | null> {
  try {
    const [newest] = await apiPublic<Announcement[]>("/announcements?limit=1");
    return newest ?? null;
  } catch {
    return null;
  }
}


function CampaignCard({ campaign }: { campaign: CampaignProgress }) {
  const unit = unitLabel(campaign.unit);

  return (
    <Card className="h-full">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium">{campaign.name}</h3>
        {campaign.completed ? <Badge tone="success">สำเร็จแล้ว</Badge> : null}
      </div>

      <p className="mt-3 tabular-nums">
        <span className="text-2xl font-semibold">{formatDecimal(campaign.value)}</span>
        {campaign.target !== null ? (
          <span className="text-muted"> / {formatDecimal(campaign.target)}</span>
        ) : null}
        <span className="ml-1 text-sm text-muted">{unit}</span>
      </p>

      {/* A campaign without a target has nothing to be a percentage of. */}
      {campaign.percent !== null ? (
        <div className="mt-3">
          <ProgressBar
            percent={barWidth(campaign.percent)}
            label={`ความคืบหน้า ${campaign.name}`}
          />
          <p className="mt-1.5 text-right text-xs text-muted tabular-nums">
            {formatDecimal(campaign.percent)}%
          </p>
        </div>
      ) : null}

      {/* Only the reward campaign tracks points; the 100 km one sends null. */}
      {campaign.points_balance !== null ? (
        <p className="mt-3 border-t border-border pt-3 text-sm">
          แต้มคงเหลือ{" "}
          <span className="font-semibold tabular-nums">
            {formatDecimal(campaign.points_balance)}
          </span>{" "}
          แต้ม
        </p>
      ) : null}
    </Card>
  );
}
