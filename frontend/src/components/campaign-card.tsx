import { Badge, Card, ProgressBar } from "@/components/ui";
import { copyFor } from "@/lib/campaign-copy";
import { barWidth, formatDecimal, unitLabel } from "@/lib/format";
import type { CampaignProgress } from "@/lib/types";

/**
 * One activity: what it is, and how far the member has got.
 *
 * Shared by the dashboard and /activities so the two cannot drift into disagreeing about
 * somebody's progress — they render the same numbers from the same response.
 *
 * The sentence under the name comes from lib/campaign-copy.ts. Members who join in the
 * middle of the year kept asking what "วันละ 10 กิโลเมตร" actually required; the name
 * alone was never going to answer that, and a card with a number on it and no explanation
 * is a card people scroll past.
 *
 * Numbers arrive as strings and are printed as strings — `formatDecimal` groups digits
 * without parsing. Points are a ledger balance and a float would round them.
 */
export function CampaignCard({ campaign }: { campaign: CampaignProgress }) {
  const unit = unitLabel(campaign.unit);
  const copy = copyFor(campaign.code);

  return (
    <Card className="h-full">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-lg font-semibold">
          {copy ? <span aria-hidden>{copy.icon} </span> : null}
          {/* The API's name, not the copy file's: a renamed campaign should read as
              renamed the moment it is saved. */}
          {campaign.name}
        </h3>
        {campaign.completed ? <Badge tone="success">สำเร็จแล้ว</Badge> : null}
      </div>

      {copy ? <p className="mt-2 text-base text-muted">{copy.blurb}</p> : null}

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
