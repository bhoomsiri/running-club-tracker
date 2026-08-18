import Link from "next/link";

import { AnnouncementBody } from "@/components/announcement-body";
import { LeaderboardRow } from "@/components/leaderboard-row";
import {
  Badge,
  ButtonLink,
  Card,
  EmptyState,
  ProgressBar,
  SectionHeading,
} from "@/components/ui";
import { apiPublic } from "@/lib/api";
import { apiServer } from "@/lib/api-server";
import { barWidth, formatDate, formatDecimal, unitLabel } from "@/lib/format";
import { isStaff, ROLE_LABELS } from "@/lib/roles";
import type {
  Announcement,
  CampaignProgress,
  Leaderboard,
  MemberSummary,
  Redemption,
} from "@/lib/types";

/**
 * Rendered on the server so the member's numbers arrive with the HTML rather than after
 * a second round trip on a phone connection. Nothing here is cached — the summary is
 * per-member and changes the moment a run is submitted.
 *
 * The screen answers two questions in order, because that is the order they are asked:
 * "how am I doing?" (the total, then each activity) and then "what do I do now?" — which
 * is always the same answer, so บันทึกผลวิ่ง is the single primary action and sits
 * directly under the number it moves. Everything below that is context: where the club
 * stands, what the club has announced, what has been redeemed.
 */

const REDEMPTION_LABELS: Record<Redemption["status"], string> = {
  pending: "รอรับของ",
  fulfilled: "รับของแล้ว",
  cancelled: "ยกเลิก",
};

const REDEMPTION_TONES: Record<Redemption["status"], "success" | "warning" | "neutral"> = {
  pending: "warning",
  fulfilled: "success",
  cancelled: "neutral",
};

export default async function DashboardPage() {
  // The news is public and the summary is not, so they are fetched by different
  // clients — but they are fetched together, because two round trips in sequence is a
  // second of blank screen on a phone.
  const [summary, news, board] = await Promise.all([
    apiServer<MemberSummary>("/me/summary"),
    latestNews(),
    standing(),
  ]);

  return (
    <>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-2xl font-bold tracking-tight">
            สวัสดี {summary.member.name}
          </h1>
          {summary.member.role !== "member" ? (
            <Badge tone="brand">{ROLE_LABELS[summary.member.role]}</Badge>
          ) : null}
        </div>
      </header>

      {/* The headline number and the one button that changes it, together. */}
      <Card className="text-center">
        <p className="text-base text-muted">ระยะสะสมรวมของคุณ</p>
        <p className="stat mt-2">
          {formatDecimal(summary.total_distance_km)}
          <span className="ml-2 text-xl font-semibold text-muted">กม.</span>
        </p>
        <ButtonLink href="/submit" className="mt-5">
          🏃 บันทึกผลวิ่ง
        </ButtonLink>
        <p className="mt-3 text-sm text-muted">ส่งรูปหลักฐาน ระบบนับให้ทันที</p>
      </Card>

      {news ? (
        <Link href="/announcements" className="mt-4 block">
          <Card className="hover:border-brand">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold text-brand">📢 ข่าวจากชมรม</p>
              <span aria-hidden className="shrink-0 text-lg text-muted">
                ›
              </span>
            </div>
            <p className="mt-1 text-lg font-semibold">{news.title}</p>
            <AnnouncementBody body={news.body} className="mt-1 line-clamp-2 text-base" />
          </Card>
        </Link>
      ) : null}

      <SectionHeading>กิจกรรมปีนี้</SectionHeading>
      {summary.campaigns.length === 0 ? (
        <EmptyState>ยังไม่มีกิจกรรมที่เปิดอยู่</EmptyState>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {summary.campaigns.map((campaign) => (
            <li key={campaign.campaign_id}>
              <CampaignCard campaign={campaign} />
            </li>
          ))}
        </ul>
      )}

      {/* Below the member's own progress, not above it: this screen is about their
          numbers first, and where they sit among everyone else second. */}
      {board ? <Standing board={board} /> : null}

      <SectionHeading>ของรางวัลที่แลกแล้ว</SectionHeading>
      {summary.redemptions.length === 0 ? (
        <EmptyState
          action={
            <ButtonLink href="/rewards" tone="secondary" fullWidth={false}>
              ดูของรางวัล
            </ButtonLink>
          }
        >
          ยังไม่ได้แลกของรางวัล — สะสมแต้มจากกิจกรรมวันละ 10 กม. ได้เลย
        </EmptyState>
      ) : (
        <ul className="grid gap-3">
          {summary.redemptions.map((redemption) => (
            <li key={redemption.id}>
              <Card className="flex items-center justify-between gap-3 py-4">
                <div>
                  <p className="text-lg font-semibold tabular-nums">
                    {formatDecimal(redemption.points_spent)} แต้ม
                  </p>
                  <p className="text-sm text-muted">
                    {formatDate(redemption.created_at)}
                  </p>
                </div>
                <Badge tone={REDEMPTION_TONES[redemption.status]}>
                  {REDEMPTION_LABELS[redemption.status]}
                </Badge>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {/* Last, and only for the few who have it: the admin screens are not part of a
          member's day. The page itself checks again and the backend refuses regardless —
          this link is navigation, not access control. */}
      {isStaff(summary.member.role) ? (
        <Link
          href="/admin"
          className="tap mt-8 justify-between rounded-card border border-border px-4 text-base font-medium"
        >
          <span>ภาพรวมสมาชิกทั้งชมรม</span>
          <span aria-hidden className="text-muted">
            ›
          </span>
        </Link>
      ) : null}
    </>
  );
}

/** The top of the club plus the member's own place in it. Best-effort like the news:
 * the dashboard's own numbers are what this page is for, and neither of the extras is
 * worth failing it. */
async function standing(): Promise<Leaderboard | null> {
  try {
    return await apiServer<Leaderboard>("/leaderboard");
  } catch {
    return null;
  }
}

function Standing({ board }: { board: Leaderboard }) {
  const top = board.entries.slice(0, 5);
  const meIsInTop = top.some((entry) => entry.member_id === board.me.member_id);

  return (
    <>
      <SectionHeading
        action={
          <Link href="/leaderboard" className="text-base font-medium text-brand">
            ดูทั้งหมด ›
          </Link>
        }
      >
        อันดับสะสมระยะ
      </SectionHeading>

      <Link href="/leaderboard" className="block">
        <Card className="text-center hover:border-brand">
          <p className="text-base text-muted">อันดับของคุณ</p>
          <p className="stat mt-1">
            #{board.me.rank}
            <span className="ml-2 text-xl font-semibold text-muted">
              จาก {board.total_members} คน
            </span>
          </p>
        </Card>
      </Link>

      {top.length === 0 ? null : (
        <ol className="mt-3 space-y-2">
          {top.map((entry) => (
            <li key={entry.member_id}>
              <LeaderboardRow
                entry={entry}
                isMe={entry.member_id === board.me.member_id}
                showPoints={false}
              />
            </li>
          ))}
          {/* Pinned below the top five when the member is not in them, so their own line
              is on this screen either way. */}
          {meIsInTop ? null : (
            <li>
              <LeaderboardRow entry={board.me} isMe showPoints={false} />
            </li>
          )}
        </ol>
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
        <h3 className="text-lg font-semibold">{campaign.name}</h3>
        {campaign.completed ? <Badge tone="success">สำเร็จแล้ว</Badge> : null}
      </div>

      <p className="mt-3 tabular-nums">
        <span className="text-3xl font-bold">{formatDecimal(campaign.value)}</span>
        {campaign.target !== null ? (
          <span className="text-lg text-muted"> / {formatDecimal(campaign.target)}</span>
        ) : null}
        <span className="ml-1.5 text-base text-muted">{unit}</span>
      </p>

      {/* A campaign without a target has nothing to be a percentage of. */}
      {campaign.percent !== null ? (
        <div className="mt-3">
          <ProgressBar
            percent={barWidth(campaign.percent)}
            label={`ความคืบหน้า ${campaign.name}`}
          />
          <p className="mt-2 text-right text-sm text-muted tabular-nums">
            {formatDecimal(campaign.percent)}%
          </p>
        </div>
      ) : null}

      {/* Only the reward campaign tracks points; the 100 km one sends null. */}
      {campaign.points_balance !== null ? (
        <p className="mt-4 border-t border-border pt-3 text-base">
          แต้มคงเหลือ{" "}
          <span className="text-xl font-bold tabular-nums">
            {formatDecimal(campaign.points_balance)}
          </span>{" "}
          แต้ม
        </p>
      ) : null}
    </Card>
  );
}
