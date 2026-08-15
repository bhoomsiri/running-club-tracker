import { PageHeader } from "@/components/page-header";
import { Badge, Card, EmptyState } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { formatDecimal } from "@/lib/format";
import type { CampaignRewards, Reward } from "@/lib/types";

import { RedeemButton } from "./redeem-button";

/**
 * The catalogue, rendered on the server so the balance and the prices arrive together.
 *
 * Affordability is not computed here: `can_redeem` comes from the backend, worked out
 * against the same balance in the same response. Deciding it on the client would mean
 * comparing two numbers that could have been fetched at different moments.
 */
export default async function RewardsPage() {
  const catalogue = await apiServer<CampaignRewards[]>("/rewards");

  return (
    <>
      <PageHeader title="รางวัล" subtitle="ใช้แต้มที่สะสมได้แลกของรางวัล" />

      {catalogue.length === 0 ? (
        <EmptyState>ยังไม่มีกิจกรรมที่สะสมแต้มในตอนนี้</EmptyState>
      ) : (
        <div className="space-y-8">
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
        </div>
      )}
    </>
  );
}

function RewardCard({ reward }: { reward: Reward }) {
  const soldOut = reward.stock === 0;

  return (
    <Card className="flex items-center justify-between gap-4">
      <div className="min-w-0">
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
    </Card>
  );
}
