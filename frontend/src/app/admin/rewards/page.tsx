import Link from "next/link";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import type { AdminReward, Campaign, MemberSummary } from "@/lib/types";

import { RewardManager } from "./reward-manager";

/**
 * Rewards belong to a campaign that pays points, so the page picks that campaign rather
 * than asking. Only one does today; if a second is added, this shows a chooser instead
 * of quietly managing the first.
 */
const POINTS_CAMPAIGN_TYPE = "daily_threshold_reward";

export default async function AdminRewardsPage({
  searchParams,
}: {
  searchParams: Promise<{ campaign?: string }>;
}) {
  const summary = await apiServer<MemberSummary>("/me/summary");
  if (summary.member.role !== "superuser") {
    redirect("/dashboard");
  }

  const campaigns = await apiServer<Campaign[]>("/admin/campaigns");
  const eligible = campaigns.filter(
    (campaign) => campaign.type === POINTS_CAMPAIGN_TYPE,
  );

  const { campaign: requested } = await searchParams;
  const campaign = eligible.find((row) => row.id === requested) ?? eligible[0];

  if (!campaign) {
    return (
      <>
        <Header />
        <EmptyState>
          ยังไม่มีกิจกรรมที่สะสมแต้ม — ของรางวัลผูกกับกิจกรรมประเภทสะสมแต้มเท่านั้น
        </EmptyState>
      </>
    );
  }

  const rewards = await apiServer<AdminReward[]>(
    `/admin/rewards?campaign_id=${campaign.id}`,
  );

  return (
    <>
      <Header />

      {eligible.length > 1 ? (
        <nav className="mb-4 flex flex-wrap gap-2">
          {eligible.map((row) => (
            <Link
              key={row.id}
              href={`/admin/rewards?campaign=${row.id}`}
              className={`min-h-12 rounded-full px-4 text-base ${
                row.id === campaign.id
                  ? "bg-brand font-semibold text-on-brand"
                  : "border border-border text-muted"
              }`}
            >
              {row.name}
            </Link>
          ))}
        </nav>
      ) : null}

      <RewardManager campaign={campaign} rewards={rewards} />
    </>
  );
}

function Header() {
  return (
    <>
      <Link href="/admin" className="text-base text-muted underline">
        ‹ กลับไปภาพรวม
      </Link>
      <header className="mt-4 mb-6">
        <h1 className="text-2xl font-bold tracking-tight">จัดการของรางวัล</h1>
        <p className="mt-2 text-base text-muted">
          เพิ่ม แก้ไข หรือเลิกแจก — ของรางวัลจะไม่ถูกลบ เพราะรายการที่สมาชิกเคยแลกไปแล้วต้องยังอ้างถึงได้
        </p>
      </header>
    </>
  );
}
