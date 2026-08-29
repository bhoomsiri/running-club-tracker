import { copyFor } from "@/lib/campaign-copy";
import { barWidth, formatDecimal, unitLabel } from "@/lib/format";
import type { CampaignProgress } from "@/lib/types";

/**
 * The campaign the dashboard leads with, drawn as a ring.
 *
 * This is the one card on the screen scoped to a campaign window; everything else is
 * lifetime. The chip says so — two numbers on one screen meaning two different periods
 * is exactly the confusion §6 of the spec exists to prevent.
 *
 * A campaign with no target has nothing to be a ring of, so it falls back to the plain
 * total. `percent` comes from the backend rather than being divided here: the policy
 * decides what progress means, and a screen that recomputed it could disagree with the
 * one on /activities.
 */
const RADIUS = 64;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function BenchmarkCard({
  campaign,
  window: campaignWindow,
}: {
  campaign: CampaignProgress;
  /** "15 ส.ค. – 30 ก.ย." — the period the number covers, if it is known. */
  window?: string;
}) {
  const unit = unitLabel(campaign.unit);
  const copy = copyFor(campaign.code);
  const percent = barWidth(campaign.percent);

  return (
    <section className="card">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold">
          {copy ? <span aria-hidden>{copy.icon} </span> : null}
          {campaign.name}
        </h3>
        <span className="shrink-0 rounded-full border border-border bg-background px-2.5 py-1 text-xs font-semibold text-muted">
          {campaignWindow ?? "แคมเปญ"}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-6">
        {campaign.percent !== null ? (
          <div className="relative size-[150px] shrink-0">
            <svg
              width={150}
              height={150}
              viewBox="0 0 150 150"
              className="-rotate-90"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`ความคืบหน้า ${campaign.name}`}
            >
              <circle
                cx={75}
                cy={75}
                r={RADIUS}
                fill="none"
                stroke="var(--surface)"
                strokeWidth={16}
              />
              <circle
                cx={75}
                cy={75}
                r={RADIUS}
                fill="none"
                stroke="var(--brand)"
                strokeWidth={16}
                strokeLinecap="round"
                strokeDasharray={CIRCUMFERENCE}
                strokeDashoffset={CIRCUMFERENCE * (1 - percent / 100)}
              />
            </svg>
            <div className="absolute inset-0 grid place-content-center text-center">
              <b className="text-3xl font-bold tabular-nums">
                {formatDecimal(campaign.percent)}%
              </b>
              {campaign.target !== null ? (
                <span className="text-xs text-muted tabular-nums">
                  ของ {formatDecimal(campaign.target)} {unit}
                </span>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="min-w-48 flex-1">
          {copy ? <p className="text-sm text-muted">{copy.blurb}</p> : null}
          <p className="mt-1 tabular-nums">
            <span className="text-4xl font-bold tracking-tight">
              {formatDecimal(campaign.value)}
            </span>
            {campaign.target !== null ? (
              <span className="text-lg font-semibold text-muted">
                {" "}
                / {formatDecimal(campaign.target)} {unit}
              </span>
            ) : (
              <span className="ml-1.5 text-lg font-semibold text-muted">{unit}</span>
            )}
          </p>

          {/* Only the reward campaign tracks points; the distance one sends null. */}
          {campaign.points_balance !== null ? (
            <p className="mt-4 inline-flex items-center gap-2 rounded-card bg-brand-tint px-3.5 py-2 font-bold text-brand">
              <span aria-hidden>★</span> แต้มสะสม
              <span className="text-xl tabular-nums">
                {formatDecimal(campaign.points_balance)}
              </span>
              แต้ม
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
