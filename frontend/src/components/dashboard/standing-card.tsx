import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { formatCount, formatDecimal } from "@/lib/format";
import type { Leaderboard } from "@/lib/types";

/**
 * Where the member sits in the club, and the few people above them.
 *
 * Their own line is pinned at the top whatever their rank, which is the whole point of
 * the backend sending `me` alongside the list: someone in 60th place opening a top five
 * and not finding themselves has learned nothing.
 *
 * Distances here are lifetime, the same set the member's own total is made of, so the
 * number beside their name on this card and the number on their own card agree.
 */
const TOP = 5;

const MEDALS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export function StandingCard({ board }: { board: Leaderboard }) {
  const top = board.entries.slice(0, TOP);

  return (
    <section className="card">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">🏆 อันดับสะสมระยะ</h3>
        <Link href="/leaderboard" className="shrink-0 text-sm font-semibold text-brand">
          ดูทั้งหมด ›
        </Link>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 rounded-card bg-brand-tint px-4 py-3">
        <div>
          <p className="text-sm font-semibold text-brand">อันดับของคุณ</p>
          <p className="text-3xl font-bold text-brand tabular-nums">
            #{board.me.rank}
            <span className="ml-1.5 text-base font-semibold">
              จาก {formatCount(board.total_members)} คน
            </span>
          </p>
        </div>
        <p className="shrink-0 text-right text-sm text-brand">
          สะสม
          <b className="block text-xl tabular-nums">
            {formatDecimal(board.me.total_distance_km)} กม.
          </b>
        </p>
      </div>

      {top.length === 0 ? null : (
        <ol className="mt-4 flex flex-col gap-2">
          {top.map((entry) => {
            const isMe = entry.member_id === board.me.member_id;
            return (
              <li
                key={entry.member_id}
                className={`flex items-center gap-3 rounded-card border px-3 py-2 ${
                  isMe ? "border-brand bg-brand-tint" : "border-border bg-surface"
                }`}
              >
                <span className="w-6 shrink-0 text-center text-lg font-bold tabular-nums">
                  {MEDALS[entry.rank] ?? (
                    <span className="text-base text-muted">{entry.rank}</span>
                  )}
                </span>
                <Avatar
                  name={entry.name}
                  imageUrl={entry.image_url}
                  seed={entry.member_id}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {entry.name}
                    {isMe ? <span className="ml-1.5 text-sm text-brand">· คุณ</span> : null}
                  </p>
                  <p className="text-xs text-muted tabular-nums">
                    {formatCount(entry.run_count)} ครั้ง
                  </p>
                </div>
                <p className="shrink-0 text-right font-bold tabular-nums">
                  {formatDecimal(entry.total_distance_km)}
                  <span className="ml-1 text-xs font-semibold text-muted">กม.</span>
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
