import Link from "next/link";

import { AnnouncementBody } from "@/components/announcement-body";
import { CampaignCard } from "@/components/campaign-card";
import { LeaderboardRow } from "@/components/leaderboard-row";
import { Badge, ButtonLink, Card, EmptyState, SectionHeading } from "@/components/ui";
import { apiPublic } from "@/lib/api";
import { apiServer } from "@/lib/api-server";
import { formatDate, formatDecimal } from "@/lib/format";
import { getMySummary } from "@/lib/me";
import { ROLE_LABELS } from "@/lib/roles";
import type {
  Announcement,
  CampaignProgress,
  Leaderboard,
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
    getMySummary(),
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

      <SectionHeading
        action={
          <Link href="/activities" className="text-base font-medium text-brand">
            ดูทั้งหมด ›
          </Link>
        }
      >
        กิจกรรมปีนี้
      </SectionHeading>
      {summary.campaigns.length === 0 ? (
        <EmptyState>ยังไม่มีกิจกรรมที่เปิดอยู่</EmptyState>
      ) : (
        <Campaigns campaigns={summary.campaigns} />
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

      {/* The admin link used to sit here, at the bottom of a member's own screen. It is
          in the header now, beside the avatar: staff reach for it from every page, not
          only after scrolling past their redemptions. */}
    </>
  );
}

/**
 * Two activities fit side by side; more than two do not.
 *
 * Past that the cards go into a horizontal snap scroller rather than a taller and taller
 * column — the dashboard's job is to show the member their standing at a glance, and an
 * activity list that pushes everything else off the screen defeats it. `ดูทั้งหมด` above
 * is the way to see them all.
 */
function Campaigns({ campaigns }: { campaigns: CampaignProgress[] }) {
  if (campaigns.length <= 2) {
    return (
      <ul className="grid gap-4 sm:grid-cols-2">
        {campaigns.map((campaign) => (
          <li key={campaign.campaign_id}>
            <CampaignCard campaign={campaign} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    // Negative margins let the row bleed to the screen edge, so a half-visible next card
    // says "there is more this way" without a scrollbar to explain it.
    <ul className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2">
      {campaigns.map((campaign) => (
        <li
          key={campaign.campaign_id}
          className="w-[82%] shrink-0 snap-start sm:w-[calc(50%-0.5rem)]"
        >
          <CampaignCard campaign={campaign} />
        </li>
      ))}
    </ul>
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
