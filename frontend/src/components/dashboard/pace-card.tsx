import { MetricCard, MetricEmpty } from "@/components/dashboard/metric-card";
import { formatPace } from "@/lib/format";
import type { RunPace } from "@/lib/types";

/**
 * Average pace, with the trend of the last few runs under it.
 *
 * The average is total time ÷ total distance, computed on the backend as a Decimal — a
 * mean of each run's pace is a different number, and it lets a 1 km jog weigh as much as
 * a 20 km long run. The caption says lower is faster, because a line that falls while
 * you improve is the opposite of every other chart on this screen.
 *
 * Fewer than two runs draws no line: a trend through one point is not a trend, and a
 * flat line would suggest a steadiness the data does not show.
 */
const TREND_MIN_POINTS = 2;

export function PaceCard({
  averagePace,
  recentPaces,
}: {
  averagePace: string | null;
  recentPaces: RunPace[];
}) {
  const formatted = formatPace(averagePace);

  return (
    <MetricCard
      label="Pace เฉลี่ย"
      period="ทั้งหมด"
      accent="blue"
      icon={
        <svg
          width={20}
          height={20}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="12" cy="12" r="2" />
          <path d="M12 12l4-4" />
          <path d="M4 18a9 9 0 1 1 16 0" />
        </svg>
      }
      note={
        recentPaces.length >= TREND_MIN_POINTS
          ? `แนวโน้ม ${recentPaces.length} ครั้งล่าสุด · ต่ำ = เร็วขึ้น`
          : undefined
      }
    >
      {formatted === null ? (
        <MetricEmpty>ยังไม่มีผลวิ่ง</MetricEmpty>
      ) : (
        <>
          <p className="text-3xl font-bold tabular-nums">
            {formatted}
            <span className="ml-1.5 text-base font-semibold text-muted">/กม.</span>
          </p>
          {recentPaces.length >= TREND_MIN_POINTS ? (
            <Sparkline paces={recentPaces} />
          ) : null}
        </>
      )}
    </MetricCard>
  );
}

const WIDTH = 220;
const HEIGHT = 44;
const PADDING = 5;

/**
 * The trend line. Floats here land in SVG coordinates and nowhere else — the same trade
 * the progress bar and the week chart make, and the reason no pace the member reads is
 * ever derived from these.
 *
 * Drawn inverted: pace falls as a runner gets faster, so the line is flipped to put
 * "faster" at the top, where every reader expects better to be. Said so in the caption
 * as well, because a chart that needs explaining explains itself badly.
 */
function Sparkline({ paces }: { paces: RunPace[] }) {
  const values = paces.map((pace) => Number(pace.pace_min_per_km));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;

  const points = values.map((value, index) => {
    const x = PADDING + (index * (WIDTH - PADDING * 2)) / (values.length - 1);
    // A flat week has no span to scale by; put the line down the middle rather than
    // dividing by zero.
    const ratio = span === 0 ? 0.5 : (value - min) / span;
    const y = PADDING + ratio * (HEIGHT - PADDING * 2);
    return [x, y] as const;
  });

  const last = points[points.length - 1];

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width="100%"
      height={HEIGHT}
      preserveAspectRatio="none"
      aria-hidden
      className="mt-3"
    >
      <polyline
        fill="none"
        stroke="var(--brand)"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points.map(([x, y]) => `${x},${y}`).join(" ")}
      />
      <circle cx={last[0]} cy={last[1]} r={3.5} fill="var(--brand)" />
    </svg>
  );
}
