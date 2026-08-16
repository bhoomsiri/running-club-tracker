import { formatDecimal } from "@/lib/format";
import type { LeaderboardEntry } from "@/lib/types";

/**
 * One line of the standing, shared by the leaderboard page and the dashboard card so a
 * member is shown the same thing in both places.
 *
 * The rank comes from the backend, ties and all — two members on 40 km are both 2nd and
 * the next is 4th, and this component never has to work that out for itself.
 */

const MEDALS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

const PODIUM: Record<number, string> = {
  1: "border-amber-400/60 bg-amber-400/10",
  2: "border-slate-400/60 bg-slate-400/10",
  3: "border-orange-500/50 bg-orange-500/10",
};

export function LeaderboardRow({
  entry,
  isMe,
  showPoints = true,
}: {
  entry: LeaderboardEntry;
  isMe: boolean;
  showPoints?: boolean;
}) {
  const medal = MEDALS[entry.rank];

  return (
    <div
      className={`flex min-h-16 items-center gap-3 rounded-card border p-3 ${
        isMe ? "border-brand bg-brand-tint" : (PODIUM[entry.rank] ?? "border-border bg-surface")
      }`}
    >
      <span className="w-10 shrink-0 text-center text-2xl tabular-nums">
        {medal ?? <span className="text-lg font-semibold text-muted">{entry.rank}</span>}
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-base font-semibold">
          {entry.name}
          {isMe ? <span className="ml-1.5 text-sm text-brand">(คุณ)</span> : null}
        </p>
        <p className="text-sm text-muted tabular-nums">
          {entry.run_count} ครั้ง
          {showPoints && entry.points !== null
            ? ` · ${formatDecimal(entry.points)} แต้ม`
            : ""}
        </p>
      </div>

      <p className="shrink-0 text-right tabular-nums">
        <span className="text-xl font-bold">{formatDecimal(entry.total_distance_km)}</span>
        <span className="ml-1 text-sm text-muted">กม.</span>
      </p>
    </div>
  );
}
