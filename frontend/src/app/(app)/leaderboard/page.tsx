import Link from "next/link";

import { LeaderboardRow } from "@/components/leaderboard-row";
import { PageHeader } from "@/components/page-header";
import { Card, EmptyState } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { formatDecimal } from "@/lib/format";
import type { Leaderboard } from "@/lib/types";

/**
 * The whole club, furthest first.
 *
 * The caller's own line comes down with the list and is pinned to the top of the page,
 * because the question someone opens this page with is "where am I?" — and scrolling a
 * hundred names looking for your own is a poor way to be told.
 *
 * Ties genuinely share a place: two members on 40 km are both 2nd, and the next is 4th.
 * The rank comes from the backend so the page never has to decide that for itself.
 */
export default async function LeaderboardPage() {
  const board = await apiServer<Leaderboard>("/leaderboard");

  return (
    <>
      <PageHeader
        title="อันดับสะสมระยะ"
        subtitle="ระยะสะสมของสมาชิกทุกคน อัปเดตทุกครั้งที่มีคนส่งผลวิ่ง"
      />

      <Card className="mb-5 text-center">
        <p className="text-base text-muted">อันดับของคุณ</p>
        <p className="stat mt-2">
          #{board.me.rank}
          <span className="ml-2 text-xl font-semibold text-muted">
            จาก {board.total_members} คน
          </span>
        </p>
        <p className="mt-3 text-base text-muted tabular-nums">
          สะสมแล้ว {formatDecimal(board.me.total_distance_km)} กม. ·{" "}
          {board.me.run_count} ครั้ง
        </p>
      </Card>

      {board.entries.length === 0 ? (
        <EmptyState>
          ยังไม่มีใครส่งผลวิ่ง —{" "}
          <Link href="/submit" className="text-brand underline">
            เป็นคนแรกเลย
          </Link>
        </EmptyState>
      ) : (
        <>
          {board.points_campaign_name !== null ? (
            <p className="mb-2 text-sm text-muted">
              คอลัมน์แต้มมาจากกิจกรรม {board.points_campaign_name}
            </p>
          ) : null}

          <ol className="space-y-2">
            {board.entries.map((entry) => (
              <li key={entry.member_id}>
                <LeaderboardRow
                  entry={entry}
                  isMe={entry.member_id === board.me.member_id}
                />
              </li>
            ))}
          </ol>
        </>
      )}

      <p className="mt-6 text-center text-sm text-muted">
        นับเฉพาะผลวิ่งที่ผ่านการตรวจสอบ — รายการที่ไม่ผ่านจะไม่ถูกนับ
      </p>
    </>
  );
}
