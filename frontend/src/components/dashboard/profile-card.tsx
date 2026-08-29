import { Avatar } from "@/components/avatar";
import { bandFor } from "@/lib/bmi";
import { formatCount, formatDecimal } from "@/lib/format";
import type { CampaignProgress, HealthComparison, Member } from "@/lib/types";

/**
 * Who the member is, and the four numbers they came to check.
 *
 * The line under the name is their position and department — real fields, both of them.
 * The mockup had "สมาชิกตั้งแต่ ส.ค. 2569" there, and `MemberResponse` carries no join
 * date, so that line is what the data can actually say rather than a date invented to
 * fill the space.
 *
 * Every stat below can be absent, and each says so in its own words: no weight recorded
 * is not the same statement as no active campaign, and neither is a zero.
 */
export function ProfileCard({
  member,
  runCount,
  goal,
  health,
}: {
  member: Member;
  runCount: number;
  /** The campaign the target comes from, if one is running. */
  goal: CampaignProgress | null;
  health: HealthComparison | null;
}) {
  const weight = (health?.after ?? health?.before)?.weight_kg ?? null;
  const bmi = health?.bmi_after ?? health?.bmi_before ?? null;
  const band = bmi ? bandFor(bmi) : null;

  return (
    <section className="card">
      <div className="flex items-center gap-4">
        <Avatar
          name={member.name}
          imageUrl={member.image_url}
          size="lg"
          seed={member.id}
        />
        <div className="min-w-0">
          <h2 className="truncate text-xl font-bold">{member.name}</h2>
          {member.position || member.department ? (
            <p className="truncate text-sm text-muted">
              {[member.position, member.department].filter(Boolean).join(" · ")}
            </p>
          ) : null}
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-y-4 border-t border-border pt-4 sm:grid-cols-4">
        <Stat label="น้ำหนัก" value={weight && formatDecimal(weight)} unit="กก." />
        <Stat
          label="เป้าหมาย"
          value={goal?.target ? formatDecimal(goal.target) : null}
          unit={goal?.target ? "กม." : undefined}
          empty="ยังไม่มีแคมเปญ"
        />
        <Stat label="BMI" value={bmi && formatDecimal(bmi)} badge={band?.label} />
        <Stat label="วิ่งแล้ว" value={formatCount(runCount)} unit="ครั้ง" />
      </dl>
    </section>
  );
}

function Stat({
  label,
  value,
  unit,
  badge,
  empty = "ยังไม่มีข้อมูล",
}: {
  label: string;
  value: string | null;
  unit?: string;
  badge?: string;
  empty?: string;
}) {
  return (
    <div className="border-border px-1 sm:not-last:border-r sm:px-3">
      <dt className="text-xs text-muted">{label}</dt>
      {value === null ? (
        <dd className="mt-0.5 text-sm text-muted">{empty}</dd>
      ) : (
        <dd className="mt-0.5">
          <span className="text-xl font-bold tabular-nums">{value}</span>
          {unit ? <span className="ml-1 text-xs font-semibold text-muted">{unit}</span> : null}
          {badge ? <span className="mt-1 block text-xs text-muted">{badge}</span> : null}
        </dd>
      )}
    </div>
  );
}
