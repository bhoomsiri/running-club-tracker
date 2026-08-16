import { PageHeader } from "@/components/page-header";
import { Badge, Card, EmptyState } from "@/components/ui";
import { ZoomableImage } from "@/components/zoomable-image";
import { apiServer } from "@/lib/api-server";
import { formatDecimal, unitLabel } from "@/lib/format";
import type { CampaignProgress, CampaignRewards, MemberSummary, Reward } from "@/lib/types";

import { RedeemButton } from "./redeem-button";

/**
 * The catalogue, rendered on the server so the balance and the prices arrive together.
 *
 * Affordability is not computed here: `can_redeem` comes from the backend, worked out
 * against the same balance in the same response. Deciding it on the client would mean
 * comparing two numbers that could have been fetched at different moments.
 *
 * `/rewards` only carries campaigns that pay points, so the 100 km challenge is absent
 * from it entirely. Its prize is real but not a catalogue row — nothing is spent to get
 * it — so the summary is fetched as well and those campaigns get a note instead of
 * silence. Being told the shirt is coming is the answer to "what do I get for this?";
 * an empty page is not.
 */

/** Placeholder copy, keyed by campaign code: the club has said what the prize is, but it
 * is not a row in any table yet, so this one line lives here rather than coming from the
 * backend. Keyed rather than global so a second non-points campaign does not silently
 * inherit the shirt. Delete the entry once the reward exists as data. */
const PLANNED_PRIZE: Record<string, string> = {
  "hundred-km-2026": "เสื้อ finisher 2026",
};

export default async function RewardsPage() {
  const [catalogue, summary] = await Promise.all([
    apiServer<CampaignRewards[]>("/rewards"),
    apiServer<MemberSummary>("/me/summary"),
  ]);

  // A null balance is the backend saying this campaign's policy tracks no points, which
  // is exactly the set that never reaches the catalogue.
  const withoutCatalogue = summary.campaigns.filter(
    (campaign) => campaign.points_balance === null,
  );

  return (
    <>
      <PageHeader title="รางวัล" subtitle="ใช้แต้มที่สะสมได้แลกของรางวัล" />

      <div className="space-y-8">
        {catalogue.length === 0 && withoutCatalogue.length === 0 ? (
          <EmptyState>ยังไม่มีกิจกรรมที่สะสมแต้มในตอนนี้</EmptyState>
        ) : null}

        {catalogue.map((campaign) => (
          <section key={campaign.campaign_id}>
            <Card className="mb-4 text-center">
              <p className="text-sm text-muted">{campaign.name}</p>
              <p className="mt-1 text-4xl font-semibold tabular-nums">
                {formatDecimal(campaign.points_balance)}
                <span className="ml-1.5 text-base font-normal text-muted">แต้ม</span>
              </p>
            </Card>

            {campaign.rewards.length === 0 ? (
              <EmptyState>
                ยังไม่มีของรางวัล ผู้ดูแลกำลังจัดเตรียม — สะสมแต้มไว้ก่อนได้เลย
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {campaign.rewards.map((reward) => (
                  <li key={reward.id}>
                    <RewardCard reward={reward} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}

        {withoutCatalogue.map((campaign) => (
          <ComingSoon key={campaign.campaign_id} campaign={campaign} />
        ))}
      </div>
    </>
  );
}

function ComingSoon({ campaign }: { campaign: CampaignProgress }) {
  return (
    <section>
      <Card className="border-dashed">
        <div className="flex items-start gap-3">
          <span aria-hidden className="text-2xl">
            🎽
          </span>
          <div className="min-w-0">
            <p className="font-medium">รางวัลสำหรับ{campaign.name}</p>
            <p className="mt-1 text-sm">
              {PLANNED_PRIZE[campaign.code] !== undefined
                ? `${PLANNED_PRIZE[campaign.code]} — กำลังจัดเตรียม เร็ว ๆ นี้`
                : "ผู้ดูแลกำลังจัดเตรียมรางวัล เร็ว ๆ นี้"}
            </p>
            <p className="mt-2 text-sm text-muted tabular-nums">
              ตอนนี้คุณสะสมได้ {formatDecimal(campaign.value)}
              {campaign.target !== null ? ` / ${formatDecimal(campaign.target)}` : ""}{" "}
              {unitLabel(campaign.unit)} — ระยะที่ทำไว้แล้วนับครบทุกกิโลเมตร
              ไม่ต้องใช้แต้มแลก
            </p>
          </div>
        </div>
      </Card>
    </section>
  );
}

function RewardCard({ reward }: { reward: Reward }) {
  const soldOut = reward.stock === 0;

  return (
    <Card>
      <div className="flex items-center gap-4">
        {reward.image_url !== null ? (
          <ZoomableImage
            src={reward.image_url}
            alt={reward.name}
            className="h-20 w-20 rounded-lg sm:h-24 sm:w-24"
          />
        ) : null}

        <div className="min-w-0 flex-1">
          <p className="font-medium">{reward.name}</p>
          <p className="mt-0.5 text-sm text-muted tabular-nums">
            ใช้ {formatDecimal(reward.points_cost)} แต้ม
          </p>
          <p className="mt-1.5">
            {soldOut ? (
              <Badge>ของหมด</Badge>
            ) : (
              <span className="text-xs text-muted tabular-nums">
                เหลือ {reward.stock} ชิ้น
              </span>
            )}
          </p>
        </div>

        <RedeemButton
          rewardId={reward.id}
          rewardName={reward.name}
          // The two reasons the backend actually withholds `can_redeem`, kept apart so
          // the member is told which one applies rather than just being greyed out.
          disabledReason={
            reward.can_redeem ? null : soldOut ? "ของหมดแล้ว" : "แต้มยังไม่พอ"
          }
        />
      </div>
    </Card>
  );
}
