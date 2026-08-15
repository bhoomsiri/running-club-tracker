"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card } from "@/components/ui";
import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDate } from "@/lib/format";
import { todayLocal } from "@/lib/run-form";
import type {
  CampaignProgress,
  HealthComparison,
  HealthPhase,
  HealthRecord,
} from "@/lib/types";

/**
 * Recording one set of measurements.
 *
 * Nothing here is logged, not to the console and not into an error message — these are
 * health values, and a console line in a shared browser or a crash report is a place
 * they must never end up. Failures are reported by status, never by echoing the body.
 *
 * Every vital is optional. A member who only wants to record their weight should be
 * able to, and a blank field is left out of the request entirely rather than sent as
 * zero, which would be a measurement nobody took.
 */

type Vital = {
  key: "weight_kg" | "height_cm";
  label: string;
  hint: string;
  decimal: boolean;
};

// Weight and height only. The backend still accepts resting heart rate and blood
// pressure, and the columns hold what members entered before — but the club is not
// taking clinical measurements, and asking for a blood pressure reading nobody is
// equipped to take invites numbers that mean nothing. What these two are for is BMI.
const VITALS: Vital[] = [
  { key: "weight_kg", label: "น้ำหนัก (กก.)", hint: "เช่น 62.5", decimal: true },
  { key: "height_cm", label: "ส่วนสูง (ซม.)", hint: "เช่น 170", decimal: true },
];

const PHASES: { value: HealthPhase; label: string; hint: string }[] = [
  { value: "before", label: "ก่อนกิจกรรม", hint: "วัดตอนเริ่มต้น" },
  { value: "after", label: "หลังกิจกรรม", hint: "วัดตอนกิจกรรมจบ" },
];

export function HealthForm({
  campaigns,
  comparisons,
}: {
  campaigns: CampaignProgress[];
  comparisons: HealthComparison[];
}) {
  const api = useApi();
  const router = useRouter();

  const [campaignId, setCampaignId] = useState(campaigns[0]?.campaign_id ?? "");
  const [phase, setPhase] = useState<HealthPhase>("before");
  const [measuredOn, setMeasuredOn] = useState(todayLocal);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (campaigns.length === 0) {
    return (
      <Card>
        <p className="text-sm text-muted">
          ยังไม่มีกิจกรรมที่เปิดอยู่ จึงยังบันทึกข้อมูลสุขภาพไม่ได้
        </p>
      </Card>
    );
  }

  const filled = VITALS.filter((vital) => (values[vital.key] ?? "").trim() !== "");
  const orderProblem = checkOrder(comparisons, campaignId, phase, measuredOn);
  const canSave =
    campaignId !== "" &&
    measuredOn !== "" &&
    filled.length > 0 &&
    orderProblem === null &&
    !busy;

  async function onSave() {
    if (!canSave) return;
    setError(null);
    setSaved(false);
    setBusy(true);

    // Only what was actually entered. Decimals go as strings so nothing is rounded on
    // the way; the two integers are counts and go as numbers.
    const vitals: Record<string, string | number> = {};
    for (const vital of filled) {
      const raw = (values[vital.key] ?? "").trim();
      vitals[vital.key] = vital.decimal ? raw : Number(raw);
    }

    try {
      await api<HealthRecord>("/health", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: campaignId,
          phase,
          measured_on: measuredOn,
          ...vitals,
        }),
      });
      setValues({});
      setSaved(true);
      router.refresh();
    } catch (saveError) {
      setError(healthErrorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="font-medium">บันทึกข้อมูลสุขภาพ</h2>

      <div className="mt-4 space-y-4">
        <div>
          <label htmlFor="campaign" className="mb-1.5 block text-sm font-medium">
            กิจกรรม
          </label>
          <select
            id="campaign"
            value={campaignId}
            onChange={(event) => setCampaignId(event.target.value)}
            className={inputClass}
          >
            {campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.name}
              </option>
            ))}
          </select>
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-medium">ช่วงที่วัด</legend>
          <div className="grid grid-cols-2 gap-2">
            {PHASES.map((option) => (
              <label
                key={option.value}
                className={`cursor-pointer rounded-lg border px-3 py-2.5 text-center ${
                  phase === option.value ? "border-brand bg-brand/10" : "border-border"
                }`}
              >
                <input
                  type="radio"
                  name="phase"
                  value={option.value}
                  checked={phase === option.value}
                  onChange={() => setPhase(option.value)}
                  className="sr-only"
                />
                <span className="block text-sm font-medium">{option.label}</span>
                <span className="block text-xs text-muted">{option.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="measured-on" className="mb-1.5 block text-sm font-medium">
            วันที่วัด
          </label>
          <input
            id="measured-on"
            type="date"
            value={measuredOn}
            max={todayLocal()}
            onChange={(event) => setMeasuredOn(event.target.value)}
            className={inputClass}
          />
          {orderProblem ? (
            <p
              role="alert"
              className="mt-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200"
            >
              {orderProblem}
            </p>
          ) : null}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {VITALS.map((vital) => (
            <div key={vital.key}>
              <label htmlFor={vital.key} className="mb-1.5 block text-sm font-medium">
                {vital.label}
              </label>
              <input
                id={vital.key}
                type="text"
                inputMode={vital.decimal ? "decimal" : "numeric"}
                autoComplete="off"
                placeholder={vital.hint}
                value={values[vital.key] ?? ""}
                onChange={(event) =>
                  setValues((current) => ({
                    ...current,
                    [vital.key]: event.target.value,
                  }))
                }
                className={inputClass}
              />
            </div>
          ))}
        </div>
        <p className="text-xs text-muted">
          กรอกเฉพาะช่องที่ต้องการได้ ช่องที่เว้นว่างจะไม่ถูกส่งและไม่ถูกเก็บ
        </p>
      </div>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
      {saved ? (
        <p className="mt-4 text-sm text-emerald-600 dark:text-emerald-400">
          บันทึกเรียบร้อยแล้ว
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void onSave()}
        disabled={!canSave}
        className="mt-5 w-full rounded-lg bg-brand px-4 py-3.5 font-medium text-white active:opacity-80 disabled:opacity-40"
      >
        {busy ? "กำลังบันทึก…" : "บันทึก"}
      </button>
    </Card>
  );
}

const inputClass =
  "w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base outline-none focus:border-brand";

/**
 * The same rule the backend enforces, checked here so the member is told before they
 * press save rather than by a rejection afterwards. The backend is still the control —
 * this copy of the numbers could be stale, and only its answer counts.
 *
 * ISO dates compare correctly as strings, so no Date parsing is needed (and none of the
 * timezone trouble that comes with it).
 */
function checkOrder(
  comparisons: HealthComparison[],
  campaignId: string,
  phase: HealthPhase,
  measuredOn: string,
): string | null {
  const existing = comparisons.find((c) => c.campaign_id === campaignId);
  if (!existing || measuredOn === "") return null;

  if (phase === "after" && existing.before !== null) {
    return measuredOn < existing.before.measured_on
      ? `วันที่วัดหลังกิจกรรมต้องไม่ก่อนวันที่วัดก่อนกิจกรรม (${formatDate(existing.before.measured_on)})`
      : null;
  }
  if (phase === "before" && existing.after !== null) {
    return measuredOn > existing.after.measured_on
      ? `วันที่วัดก่อนกิจกรรมต้องไม่หลังวันที่วัดหลังกิจกรรม (${formatDate(existing.after.measured_on)})`
      : null;
  }
  return null;
}

function healthErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return messageFor(error);
  switch (error.status) {
    case 403:
      // The backend enforces the same gate this screen does; reaching it means consent
      // changed in another tab.
      return "ต้องให้ความยินยอมก่อนจึงจะบันทึกข้อมูลสุขภาพได้";
    case 422:
      // Deliberately no echo of which value was out of range — the detail would carry
      // the measurement itself.
      return "ค่าที่กรอกอยู่นอกช่วงที่รับได้ กรุณาตรวจสอบอีกครั้ง";
    default:
      return messageFor(error);
  }
}
