"use client";

import { useState } from "react";

import { BmiScale } from "@/components/bmi-scale";
import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { todayLocal } from "@/lib/run-form";
import type { CampaignProgress, HealthRecord } from "@/lib/types";

/**
 * The starting weight and height.
 *
 * Both are required here, unlike the general health form: a baseline with only one of
 * them yields no BMI, so there would be nothing for the "after" measurement to be
 * compared against — and by the time anyone notices, the moment to take it has passed.
 *
 * Sent as strings. The backend stores them as Decimal so a value survives exactly as
 * entered, and BMI is derived from them rather than stored, so it can never drift out
 * of agreement with the numbers it came from.
 */

const DECIMAL_RE = /^\d{1,3}(\.\d{1,2})?$/;

export function BaselineForm({
  campaigns,
  submitLabel,
  onSaved,
}: {
  campaigns: CampaignProgress[];
  submitLabel: string;
  onSaved: () => void;
}) {
  const api = useApi();

  const [campaignId, setCampaignId] = useState(campaigns[0]?.campaign_id ?? "");
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const weightOk = DECIMAL_RE.test(weight.trim()) && /[1-9]/.test(weight);
  const heightOk = DECIMAL_RE.test(height.trim()) && /[1-9]/.test(height);
  const canSave = campaignId !== "" && weightOk && heightOk && !busy;

  // Previewed from the strings without converting them: the scale only needs to know
  // which band to highlight, and the value shown is still what the member typed.
  const previewBmi =
    weightOk && heightOk ? computeBmiForPreview(weight.trim(), height.trim()) : null;

  async function onSubmit() {
    if (!canSave) return;
    setError(null);
    setBusy(true);
    try {
      await api<HealthRecord>("/health", {
        method: "POST",
        body: JSON.stringify({
          campaign_id: campaignId,
          phase: "before",
          measured_on: todayLocal(),
          weight_kg: weight.trim(),
          height_cm: height.trim(),
        }),
      });
      onSaved();
    } catch (saveError) {
      setError(
        saveError instanceof ApiError && saveError.status === 403
          ? "ต้องให้ความยินยอมก่อนจึงจะบันทึกข้อมูลสุขภาพได้"
          : saveError instanceof ApiError && saveError.status === 422
            ? "ค่าที่กรอกอยู่นอกช่วงที่รับได้ กรุณาตรวจสอบอีกครั้ง"
            : messageFor(saveError),
      );
    } finally {
      setBusy(false);
    }
  }

  if (campaigns.length === 0) {
    return (
      <p className="text-sm text-muted">
        ยังไม่มีกิจกรรมที่เปิดอยู่ จึงยังบันทึกค่าตั้งต้นไม่ได้
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {campaigns.length > 1 ? (
        <div>
          <label htmlFor="baseline-campaign" className="mb-1.5 block text-sm font-medium">
            กิจกรรม
          </label>
          <select
            id="baseline-campaign"
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
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="baseline-weight" className="mb-1.5 block text-sm font-medium">
            น้ำหนัก (กก.)
          </label>
          <input
            id="baseline-weight"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={weight}
            onChange={(event) => setWeight(event.target.value)}
            placeholder="62.5"
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="baseline-height" className="mb-1.5 block text-sm font-medium">
            ส่วนสูง (ซม.)
          </label>
          <input
            id="baseline-height"
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={height}
            onChange={(event) => setHeight(event.target.value)}
            placeholder="170"
            className={inputClass}
          />
        </div>
      </div>

      {previewBmi ? (
        <div className="rounded-xl border border-border p-3">
          <BmiScale bmi={previewBmi} caption="BMI ของคุณ" />
        </div>
      ) : (
        <p className="text-xs text-muted">
          กรอกทั้งน้ำหนักและส่วนสูงเพื่อคำนวณ BMI — ต้องมีทั้งคู่ ไม่งั้นจะไม่มีค่าตั้งต้นให้เปรียบเทียบตอนจบกิจกรรม
        </p>
      )}

      {error ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void onSubmit()}
        disabled={!canSave}
        className="w-full rounded-lg bg-brand px-4 py-3.5 font-medium text-white active:opacity-80 disabled:opacity-40"
      >
        {busy ? "กำลังบันทึก…" : submitLabel}
      </button>
    </div>
  );
}

/**
 * A preview only — the stored BMI is always the backend's, derived from the Decimals it
 * holds. This one exists so the member can see the band before they commit, and it is
 * rounded the same way (one decimal, half-up) so the two agree on screen.
 */
function computeBmiForPreview(weightKg: string, heightCm: string): string | null {
  const metres = Number(heightCm) / 100;
  if (!Number.isFinite(metres) || metres <= 0) return null;
  const value = Number(weightKg) / (metres * metres);
  if (!Number.isFinite(value)) return null;
  return value.toFixed(1);
}

const inputClass =
  "w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base outline-none focus:border-brand";
