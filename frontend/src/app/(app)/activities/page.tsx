import { CampaignCard } from "@/components/campaign-card";
import { PageHeader } from "@/components/page-header";
import { ButtonLink, EmptyState } from "@/components/ui";
import { getMySummary } from "@/lib/me";

/**
 * Every activity the club is running, with what each one asks for.
 *
 * The dashboard shows the same cards, but only as many as fit before they push the rest
 * of the screen away; this is where they all are, in full, with room for the sentence
 * that explains each one. Reached from `ดูทั้งหมด ›` beside the dashboard's heading —
 * the same way the leaderboard is, because it is the same idea.
 *
 * Progress comes from the member's own summary rather than a campaign list, so the
 * numbers here are the ones on their dashboard and cannot disagree with them.
 */
export default async function ActivitiesPage() {
  const summary = await getMySummary();

  return (
    <>
      <PageHeader
        title="กิจกรรมปีนี้"
        subtitle="ทุกกิจกรรมที่ชมรมเปิดอยู่ และความคืบหน้าของคุณในแต่ละกิจกรรม"
      />

      {summary.campaigns.length === 0 ? (
        <EmptyState>
          ยังไม่มีกิจกรรมที่เปิดอยู่ — ติดตามประกาศจากชมรมได้ที่หน้าข่าว
        </EmptyState>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {summary.campaigns.map((campaign) => (
            <li key={campaign.campaign_id}>
              <CampaignCard campaign={campaign} />
            </li>
          ))}
        </ul>
      )}

      <div className="mt-8">
        <ButtonLink href="/submit">🏃 บันทึกผลวิ่ง</ButtonLink>
        <p className="mt-3 text-center text-sm text-muted">
          ผลวิ่งครั้งเดียวนับให้ทุกกิจกรรมที่เข้าเงื่อนไข ไม่ต้องส่งซ้ำ
        </p>
      </div>
    </>
  );
}
