"use client";

import { useState } from "react";

import { BmiScale } from "@/components/bmi-scale";
import { Badge, Card } from "@/components/ui";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDate, formatDecimal } from "@/lib/format";
import { NO_RISK_NOTE, RISK_WARNING, SCREENING_SECTIONS } from "@/lib/screening-text";
import type { MemberContact, MemberHealth, MemberScreening } from "@/lib/types";

/**
 * The sensitive half of a member's page, behind a button each.
 *
 * Nothing here loads with the page, and that is the whole design. Each of these calls
 * writes an audit row, so fetching them on render would mean three rows every time
 * anyone glanced at anyone — an audit log full of glances is one nobody reads, and it
 * would put a member's cardiac history on screen for whoever was standing nearby.
 *
 * Pressing the button is the deliberate act, and the notice says plainly that it is
 * recorded. It stays visible afterwards rather than flashing once.
 */

type Section = "health" | "screening" | "contact";

const LABELS: Record<Section, { title: string; blurb: string; button: string }> = {
  health: {
    title: "ข้อมูลสุขภาพ",
    blurb: "น้ำหนัก ส่วนสูง และ BMI ก่อน/หลังกิจกรรม",
    button: "เปิดดูข้อมูลสุขภาพ",
  },
  screening: {
    title: "แบบคัดกรองก่อนออกกำลังกาย",
    blurb: "คำตอบ PAR-Q+ 11 ข้อ",
    button: "เปิดดูแบบคัดกรอง",
  },
  contact: {
    title: "ข้อมูลติดต่อและผู้ติดต่อฉุกเฉิน",
    blurb: "วันเกิด เพศ เบอร์โทร และผู้ติดต่อกรณีฉุกเฉิน",
    button: "เปิดดูข้อมูลติดต่อ",
  },
};

const SEX_LABELS: Record<string, string> = { male: "ชาย", female: "หญิง" };

export function SensitivePanel({ memberId }: { memberId: string }) {
  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
        ส่วนด้านล่างเป็นข้อมูลอ่อนไหวตาม PDPA — ระบบจะบันทึกไว้ทุกครั้งที่คุณกดเปิดดู
        ว่าใครเปิดดูของใคร เมื่อไหร่ กรุณาเปิดดูเท่าที่จำเป็น
      </p>

      <SensitiveSection section="health" memberId={memberId} />
      <SensitiveSection section="screening" memberId={memberId} />
      <SensitiveSection section="contact" memberId={memberId} />
    </div>
  );
}

function SensitiveSection({
  section,
  memberId,
}: {
  section: Section;
  memberId: string;
}) {
  const api = useApi();
  const labels = LABELS[section];

  const [data, setData] = useState<
    MemberHealth | MemberScreening | MemberContact | null
  >(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reveal() {
    setError(null);
    setBusy(true);
    try {
      // One request, one audit row, made only because someone pressed this.
      const path =
        section === "health"
          ? `/admin/members/${memberId}/health`
          : section === "screening"
            ? `/admin/members/${memberId}/screening`
            : `/admin/members/${memberId}/contact`;
      setData(await api<MemberHealth | MemberScreening | MemberContact>(path));
    } catch (revealError) {
      setError(messageFor(revealError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-lg font-semibold">{labels.title}</p>
          <p className="mt-0.5 text-sm text-muted">{labels.blurb}</p>
        </div>
        {data === null ? (
          <button
            type="button"
            onClick={() => void reveal()}
            disabled={busy}
            className="btn btn-secondary shrink-0"
          >
            {busy ? "กำลังเปิด…" : labels.button}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setData(null)}
            className="shrink-0 text-sm text-muted underline"
          >
            ซ่อน
          </button>
        )}
      </div>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}

      {data !== null ? (
        <div className="mt-4 border-t border-border pt-4">
          <p className="mb-3 text-base text-muted">
            🔒 การเปิดดูครั้งนี้ถูกบันทึกไว้แล้วตาม PDPA
          </p>
          {section === "health" ? <HealthView view={data as MemberHealth} /> : null}
          {section === "screening" ? (
            <ScreeningView view={data as MemberScreening} />
          ) : null}
          {section === "contact" ? <ContactView view={data as MemberContact} /> : null}
        </div>
      ) : null}
    </Card>
  );
}

function HealthView({ view }: { view: MemberHealth }) {
  if (view.health.length === 0) {
    return <p className="text-base text-muted">สมาชิกยังไม่ได้บันทึกข้อมูลสุขภาพ</p>;
  }

  return (
    <div className="space-y-4">
      {view.health.map((comparison) => {
        const latest = comparison.bmi_after ?? comparison.bmi_before;
        return (
          <div key={comparison.campaign_id}>
            <dl className="grid grid-cols-2 gap-3 text-sm tabular-nums">
              <Phase label="ก่อน" record={comparison.before} bmi={comparison.bmi_before} />
              <Phase label="หลัง" record={comparison.after} bmi={comparison.bmi_after} />
            </dl>
            {latest !== null ? (
              <div className="mt-3">
                <BmiScale bmi={latest} caption="BMI ล่าสุด" />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function Phase({
  label,
  record,
  bmi,
}: {
  label: string;
  record: MemberHealth["health"][number]["before"];
  bmi: string | null;
}) {
  return (
    <div>
      <Badge>{label}</Badge>
      {record === null ? (
        <p className="mt-1.5 text-muted">ยังไม่ได้บันทึก</p>
      ) : (
        <ul className="mt-1.5 space-y-0.5">
          <li>วันที่ {formatDate(record.measured_on)}</li>
          {record.weight_kg !== null ? (
            <li>น้ำหนัก {formatDecimal(record.weight_kg)} กก.</li>
          ) : null}
          {record.height_cm !== null ? (
            <li>ส่วนสูง {formatDecimal(record.height_cm)} ซม.</li>
          ) : null}
          {bmi !== null ? <li>BMI {formatDecimal(bmi)}</li> : null}
        </ul>
      )}
    </div>
  );
}

function ScreeningView({ view }: { view: MemberScreening }) {
  const screening = view.screening;
  if (screening === null) {
    return <p className="text-base text-muted">สมาชิกยังไม่ได้ทำแบบคัดกรอง</p>;
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {screening.needs_medical_advice ? (
          <Badge>ควรพบแพทย์</Badge>
        ) : (
          <Badge tone="success">ไม่พบข้อบ่งชี้</Badge>
        )}
        <span className="text-base text-muted">
          ตอบเมื่อ {formatDate(screening.screened_on)} · {screening.version}
        </span>
      </div>
      <p className="mt-2 text-sm text-muted">
        {screening.needs_medical_advice ? RISK_WARNING : NO_RISK_NOTE}
      </p>

      <ul className="mt-3 space-y-1.5">
        {SCREENING_SECTIONS.flatMap((group) => group.questions).map((question) => {
          const answer = screening.answers[question.key];
          return (
            <li
              key={question.key}
              className={`flex items-start gap-2 rounded-control px-2.5 py-2 text-base ${
                answer ? "bg-amber-500/10" : ""
              }`}
            >
              <span className="w-10 shrink-0 font-medium">
                {answer ? "ใช่" : "ไม่ใช่"}
              </span>
              <span className={answer ? "" : "text-muted"}>{question.text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ContactView({ view }: { view: MemberContact }) {
  const age = ageOn(view.birth_date);

  return (
    <dl className="space-y-1.5 text-sm">
      <Row
        label="อายุ"
        value={
          age === null || view.birth_date === null
            ? "—"
            : `${age} ปี (เกิด ${formatDate(view.birth_date)})`
        }
      />
      <Row label="เพศ" value={view.sex === null ? "—" : (SEX_LABELS[view.sex] ?? view.sex)} />
      <Row label="เบอร์โทร" value={view.phone ?? "—"} />
      <Row label="ผู้ติดต่อฉุกเฉิน" value={view.emergency_contact_name ?? "—"} />
      <Row label="เบอร์ผู้ติดต่อ" value={view.emergency_contact_phone ?? "—"} />
    </dl>
  );
}

/** Whole years lived, counting the birthday on the day itself — the same rule the
 * backend applies when it decides whether somebody is old enough to join. */
function ageOn(birthDate: string | null): number | null {
  if (birthDate === null) return null;
  const [year, month, day] = birthDate.split("-").map(Number);
  const today = new Date();
  const hadBirthday =
    today.getMonth() + 1 > month ||
    (today.getMonth() + 1 === month && today.getDate() >= day);
  return today.getFullYear() - year - (hadBirthday ? 0 : 1);
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}
