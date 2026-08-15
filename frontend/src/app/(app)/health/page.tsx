import { PageHeader } from "@/components/page-header";
import { Badge, Card, EmptyState } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { formatDate, formatDecimal } from "@/lib/format";
import type { Consent, HealthComparison, HealthRecord, MemberSummary } from "@/lib/types";

import { ConsentGate } from "./consent-gate";
import { HealthForm } from "./health-form";

/**
 * Health data, behind consent.
 *
 * The gate is applied here as well as in the backend, on purpose. The backend refuses to
 * write a record without an active consent whatever the client does — that is the part
 * that has to hold. This screen's job is that a member is never invited to type their
 * weight into a box the club has no lawful basis to keep it in.
 *
 * `active` is what decides: it is false for a consent given to wording that has since
 * changed, and a withdrawn one comes back as null. Both mean ask again.
 */
export default async function HealthPage() {
  const [consent, summary] = await Promise.all([
    apiServer<Consent | null>("/consent"),
    apiServer<MemberSummary>("/me/summary"),
  ]);

  return (
    <>
      <PageHeader
        title="ข้อมูลสุขภาพ"
        subtitle="เปรียบเทียบผลก่อนและหลังกิจกรรม"
      />

      <div className="space-y-6">
        <ConsentGate consent={consent} />

        {consent?.active === true ? (
          <HealthForm campaigns={summary.campaigns} />
        ) : null}

        <section>
          <h2 className="mb-3 text-sm font-semibold text-muted">ผลเปรียบเทียบ</h2>
          {summary.health.length === 0 ? (
            <EmptyState>
              ยังไม่มีข้อมูล — บันทึกค่าช่วง &laquo;ก่อนกิจกรรม&raquo; และ
              &laquo;หลังกิจกรรม&raquo; แล้วระบบจะเปรียบเทียบให้
            </EmptyState>
          ) : (
            <ul className="space-y-3">
              {summary.health.map((comparison) => (
                <li key={comparison.campaign_id}>
                  <ComparisonCard
                    comparison={comparison}
                    campaignName={
                      summary.campaigns.find(
                        (campaign) => campaign.campaign_id === comparison.campaign_id,
                      )?.name ?? "กิจกรรม"
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function ComparisonCard({
  comparison,
  campaignName,
}: {
  comparison: HealthComparison;
  campaignName: string;
}) {
  return (
    <Card>
      <h3 className="font-medium">{campaignName}</h3>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <PhaseColumn title="ก่อน" record={comparison.before} bmi={comparison.bmi_before} />
        <PhaseColumn title="หลัง" record={comparison.after} bmi={comparison.bmi_after} />
      </div>

      {comparison.bmi_delta !== null ? (
        <p className="mt-3 border-t border-border pt-3 text-sm">
          BMI เปลี่ยนแปลง{" "}
          <span className="font-semibold tabular-nums">
            {/* The sign is already in the string the backend sent; a leading "+" is
                added for a gain so the direction reads at a glance. */}
            {comparison.bmi_delta.startsWith("-") ? "" : "+"}
            {formatDecimal(comparison.bmi_delta)}
          </span>
        </p>
      ) : null}
    </Card>
  );
}

function PhaseColumn({
  title,
  record,
  bmi,
}: {
  title: string;
  record: HealthRecord | null;
  bmi: string | null;
}) {
  return (
    <div>
      <p className="mb-1.5">
        <Badge>{title}</Badge>
      </p>
      {record === null ? (
        <p className="text-sm text-muted">ยังไม่ได้บันทึก</p>
      ) : (
        <dl className="space-y-1 text-sm tabular-nums">
          <Row label="วันที่" value={formatDate(record.measured_on)} />
          {record.weight_kg !== null ? (
            <Row label="น้ำหนัก" value={`${formatDecimal(record.weight_kg)} กก.`} />
          ) : null}
          {record.height_cm !== null ? (
            <Row label="ส่วนสูง" value={`${formatDecimal(record.height_cm)} ซม.`} />
          ) : null}
          {bmi !== null ? <Row label="BMI" value={formatDecimal(bmi)} /> : null}
          {record.resting_hr !== null ? (
            <Row label="ชีพจร" value={`${record.resting_hr}`} />
          ) : null}
          {record.systolic !== null && record.diastolic !== null ? (
            <Row label="ความดัน" value={`${record.systolic}/${record.diastolic}`} />
          ) : null}
        </dl>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
