import Link from "next/link";

import { CampaignCard } from "@/components/campaign-card";
import { BenchmarkCard } from "@/components/dashboard/benchmark-card";
import { LatestRunCard } from "@/components/dashboard/latest-run-card";
import {
  MetricCard,
  MetricEmpty,
  MetricValue,
} from "@/components/dashboard/metric-card";
import { NewsBanner } from "@/components/dashboard/news-banner";
import { PaceCard } from "@/components/dashboard/pace-card";
import { ProfileCard } from "@/components/dashboard/profile-card";
import { StandingCard } from "@/components/dashboard/standing-card";
import { WeekChart } from "@/components/dashboard/week-chart";
import { WeightCard } from "@/components/dashboard/weight-card";
import { ButtonLink, EmptyState } from "@/components/ui";
import { apiPublic } from "@/lib/api";
import { apiServer } from "@/lib/api-server";
import { formatCount, splitDuration } from "@/lib/format";
import { getMySummary } from "@/lib/me";
import type { Announcement, Leaderboard, MemberSummary } from "@/lib/types";

/**
 * The member's own record, rendered on the server so their numbers arrive with the HTML
 * rather than after a second round trip on a phone connection. Nothing is cached — the
 * summary is per-member and changes the moment a run is submitted.
 *
 * Two periods share this screen and every card says which one it is on. The activity
 * cards are lifetime, over every run of theirs that still counts; the benchmark card is
 * a campaign window. They are different questions and they give different answers, so
 * the labels are load-bearing rather than decoration.
 *
 * No card invents a number. A count nobody recorded reads "ไม่ได้บันทึก", a partial total
 * carries how many runs it is made of, and an average over no runs is absent rather than
 * zero — a member who has not started has not run at 0 min/km.
 */
export default async function DashboardPage() {
  // The news is public and the summary is not, so they go through different clients —
  // but they are fetched together, because two sequential round trips is a second of
  // blank screen on a phone.
  const [summary, news, board] = await Promise.all([
    getMySummary(),
    latestNews(),
    standing(),
  ]);

  const { activity, member } = summary;
  // The ring needs something to be a ring of, so the campaign with a target leads and
  // the rest keep their ordinary cards below it. Picking `campaigns[0]` would have put
  // whichever came back first in the ring and dropped the other one off the screen
  // entirely — including the points balance, which only the reward campaign carries.
  const [benchmark, ...otherCampaigns] = [...summary.campaigns].sort(
    (a, b) => Number(b.target !== null) - Number(a.target !== null),
  );
  // The first comparison is the current one: the backend lists them in the order the
  // records were made, and a member has at most one screening per campaign.
  const health = summary.health[0] ?? null;
  const hasRuns = activity.run_count > 0;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">ภาพรวม</h1>
        {/* The one action this screen leads to, beside the numbers it moves. */}
        <ButtonLink href="/submit" fullWidth={false}>
          🏃 ส่งผลวิ่ง
        </ButtonLink>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(340px,2fr)_3fr]">
        <div className="flex min-w-0 flex-col gap-4">
          <ProfileCard
            member={member}
            runCount={activity.run_count}
            goal={benchmark}
            health={health}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <MetricCard
              label="แคลอรี่ที่เผา"
              period="ทั้งหมด"
              accent="rose"
              icon="🔥"
              note={<PartialNote counted={activity.calories_from_runs} of={activity.run_count} />}
            >
              {activity.calories_from_runs === 0 ? (
                <MetricEmpty>ยังไม่ได้บันทึก</MetricEmpty>
              ) : (
                <MetricValue value={formatCount(activity.total_calories)} unit="kcal" />
              )}
            </MetricCard>

            <MetricCard
              label="จำนวนก้าว"
              period="ทั้งหมด"
              accent="blue"
              icon="👟"
              note={<PartialNote counted={activity.steps_from_runs} of={activity.run_count} />}
            >
              {activity.steps_from_runs === 0 ? (
                <MetricEmpty>ยังไม่ได้บันทึก</MetricEmpty>
              ) : (
                <MetricValue value={formatCount(activity.total_steps)} />
              )}
            </MetricCard>

            <MetricCard
              label="เวลาวิ่งรวม"
              period="ทั้งหมด"
              accent="violet"
              icon="⏱"
              note={hasRuns ? `จาก ${formatCount(activity.run_count)} ครั้ง` : undefined}
            >
              {hasRuns ? <Duration seconds={activity.active_seconds} /> : (
                <MetricEmpty>ยังไม่มีผลวิ่ง</MetricEmpty>
              )}
            </MetricCard>

            <MetricCard label="จำนวนครั้งที่วิ่ง" period="ทั้งหมด" accent="amber" icon="🔁">
              {hasRuns ? (
                <MetricValue value={formatCount(activity.run_count)} unit="ครั้ง" />
              ) : (
                <MetricEmpty>ยังไม่เคยส่งผลวิ่ง</MetricEmpty>
              )}
            </MetricCard>
          </div>

          {hasRuns ? (
            <WeekChart days={activity.last_seven_days} />
          ) : (
            <EmptyState
              action={
                <ButtonLink href="/submit" tone="secondary" fullWidth={false}>
                  ส่งผลวิ่งครั้งแรก
                </ButtonLink>
              }
            >
              ยังไม่มีผลวิ่ง — ส่งรูปหลักฐานครั้งแรกแล้วกราฟจะขึ้นที่นี่
            </EmptyState>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          {benchmark ? (
            <BenchmarkCard campaign={benchmark} />
          ) : (
            <EmptyState>ยังไม่มีกิจกรรมที่เปิดอยู่</EmptyState>
          )}

          {/* Any other activity keeps the card it has on /activities, so the two screens
              cannot drift into disagreeing about somebody's progress. */}
          {otherCampaigns.map((campaign) => (
            <CampaignCard key={campaign.campaign_id} campaign={campaign} />
          ))}

          {board ? <StandingCard board={board} /> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <PaceCard
              averagePace={activity.avg_pace_min_per_km}
              recentPaces={activity.recent_paces}
            />
            {activity.latest_run ? (
              <LatestRunCard run={activity.latest_run} />
            ) : (
              <MetricCard label="การวิ่งครั้งล่าสุด" period="ล่าสุด" icon="🏃">
                <MetricEmpty>ยังไม่มีผลวิ่ง</MetricEmpty>
              </MetricCard>
            )}
          </div>

          {health ? (
            <WeightCard comparison={health} />
          ) : (
            <EmptyState
              action={
                <ButtonLink href="/health" tone="secondary" fullWidth={false}>
                  ไปหน้าสุขภาพ
                </ButtonLink>
              }
            >
              ยังไม่มีข้อมูลสุขภาพ — บันทึกน้ำหนักและส่วนสูงเพื่อดู BMI ของคุณ
            </EmptyState>
          )}
        </div>

        {/* Full width, at the foot: the club's news is context, not the member's own
            record, so it sits below everything that is. */}
        {news ? (
          <section className="lg:col-span-2">
            <h2 className="mb-2 text-xs font-bold tracking-wide text-muted uppercase">
              ประชาสัมพันธ์
            </h2>
            <NewsBanner announcement={news} />
          </section>
        ) : null}
      </div>

      <RedemptionsLink summary={summary} />
    </>
  );
}

/** "รวมจาก 18 ใน 24 ครั้งที่บันทึก", or nothing when there is nothing partial to say. */
function PartialNote({ counted, of }: { counted: number; of: number }) {
  if (counted === 0 || of === 0) return null;
  if (counted === of) return <>จากทั้ง {formatCount(of)} ครั้ง</>;
  return (
    <>
      รวมจาก{" "}
      <b className="text-foreground">
        {formatCount(counted)} ใน {formatCount(of)}
      </b>{" "}
      ครั้งที่บันทึก
    </>
  );
}

function Duration({ seconds }: { seconds: number }) {
  const { hours, minutes } = splitDuration(seconds);
  return (
    <p className="text-3xl font-bold tabular-nums">
      {hours > 0 ? (
        <>
          {formatCount(hours)}
          <span className="mx-1 text-base font-semibold text-muted">ชม.</span>
        </>
      ) : null}
      {minutes}
      <span className="ml-1 text-base font-semibold text-muted">น.</span>
    </p>
  );
}

/** Redemptions moved off the dashboard's grid and into a line: they belong to the member
 * but they are not a measurement, and /rewards is the screen that is about them. */
function RedemptionsLink({ summary }: { summary: MemberSummary }) {
  if (summary.redemptions.length === 0) return null;
  return (
    <p className="mt-5 text-sm text-muted">
      แลกของรางวัลแล้ว {formatCount(summary.redemptions.length)} รายการ ·{" "}
      <Link href="/rewards" className="font-semibold text-brand">
        ดูของรางวัล ›
      </Link>
    </p>
  );
}

/** The top of the club plus the member's own place in it. Best-effort like the news: the
 * dashboard's own numbers are what this page is for, and neither extra is worth failing
 * the whole screen over. */
async function standing(): Promise<Leaderboard | null> {
  try {
    return await apiServer<Leaderboard>("/leaderboard");
  } catch {
    return null;
  }
}

async function latestNews(): Promise<Announcement | null> {
  try {
    const [newest] = await apiPublic<Announcement[]>("/announcements?limit=1");
    return newest ?? null;
  } catch {
    return null;
  }
}
