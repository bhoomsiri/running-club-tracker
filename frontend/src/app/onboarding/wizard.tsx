"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BaselineForm } from "@/components/forms/baseline-form";
import { ProfileForm } from "@/components/forms/profile-form";
import { ScreeningForm } from "@/components/forms/screening-form";
import { Card } from "@/components/ui";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import {
  CONSENT_POINTS,
  CONSENT_PURPOSE,
} from "@/lib/consent-text";
import type {
  CampaignProgress,
  Consent,
  MemberProfile,
  OnboardingStep,
  Screening,
} from "@/lib/types";

/**
 * Four steps, one at a time.
 *
 * The order is not cosmetic: consent comes first because every step after it stores
 * sensitive personal data, and the club has no lawful basis to hold any of it until the
 * member has agreed. The wizard therefore never shows the screening or the baseline
 * before consent has been given.
 *
 * Steps the member has already completed are skipped — the backend says which are
 * outstanding, so someone who half-finished last week resumes where they stopped rather
 * than answering eleven questions again.
 */

const STEPS: { id: OnboardingStep; title: string; blurb: string }[] = [
  {
    id: "consent",
    title: "ความยินยอม",
    blurb: "ก่อนเริ่ม ชมรมขอความยินยอมในการเก็บข้อมูลสุขภาพของคุณ",
  },
  {
    id: "profile",
    title: "ข้อมูลทั่วไป",
    blurb: "ชื่อ วันเกิด เพศ ตำแหน่ง หน่วยงาน ไซส์เสื้อ และผู้ติดต่อกรณีฉุกเฉิน",
  },
  {
    id: "screening",
    title: "แบบคัดกรองก่อนออกกำลังกาย",
    blurb: "11 คำถามสั้น ๆ เพื่อดูว่าคุณควรพบแพทย์ก่อนเริ่มซ้อมหรือไม่",
  },
  {
    id: "baseline",
    title: "ค่าตั้งต้น",
    blurb: "น้ำหนักและส่วนสูงตอนเริ่ม เพื่อเทียบผลตอนจบกิจกรรม",
  },
];

export function OnboardingWizard({
  missing,
  profile,
  screening,
  campaigns,
}: {
  missing: OnboardingStep[];
  profile: MemberProfile | null;
  screening: Screening | null;
  campaigns: CampaignProgress[];
}) {
  const router = useRouter();
  const [done, setDone] = useState<OnboardingStep[]>([]);

  const outstanding = STEPS.filter(
    (step) => missing.includes(step.id) && !done.includes(step.id),
  );
  const current = outstanding[0];

  function complete(step: OnboardingStep) {
    const remaining = outstanding.filter((other) => other.id !== step);
    if (remaining.length === 0) {
      // refresh() as well as push(), so the gate in the app layout re-reads the status
      // on the server instead of bouncing the member straight back here.
      router.push("/dashboard");
      router.refresh();
      return;
    }
    setDone((current) => [...current, step]);
  }

  if (!current) {
    return (
      <Card>
        <p className="text-sm">เรียบร้อยแล้ว กำลังพาไปหน้าแดชบอร์ด…</p>
      </Card>
    );
  }

  const position = missing.indexOf(current.id) + 1;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-base font-semibold text-brand">
          ขั้นที่ {position} จาก {missing.length}
        </p>
        <div className="mt-2 flex gap-2" aria-hidden>
          {missing.map((step) => (
            <span
              key={step}
              className={`h-2.5 flex-1 rounded-full ${
                done.includes(step) || step === current.id ? "bg-brand" : "bg-border"
              }`}
            />
          ))}
        </div>
        <h2 className="mt-5 text-2xl font-bold tracking-tight">{current.title}</h2>
        <p className="mt-2 text-base text-muted">{current.blurb}</p>
      </div>

      <Card>
        {current.id === "consent" ? (
          <ConsentStep onDone={() => complete("consent")} />
        ) : null}

        {current.id === "profile" ? (
          <ProfileForm
            initial={profile}
            submitLabel="บันทึกและไปต่อ"
            onSaved={() => complete("profile")}
          />
        ) : null}

        {current.id === "screening" ? (
          <ScreeningForm
            initial={screening}
            submitLabel="บันทึกและไปต่อ"
            onSaved={() => complete("screening")}
          />
        ) : null}

        {current.id === "baseline" ? (
          <BaselineForm
            campaigns={campaigns}
            submitLabel="เสร็จสิ้น"
            onSaved={() => complete("baseline")}
          />
        ) : null}
      </Card>

      <p className="text-center text-sm text-muted">
        ทุกอย่างแก้ไขได้ภายหลังที่หน้าโปรไฟล์และหน้าข้อมูลสุขภาพ
      </p>
    </div>
  );
}

function ConsentStep({ onDone }: { onDone: () => void }) {
  const api = useApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function grant() {
    setError(null);
    setBusy(true);
    try {
      await api<Consent>("/consent", { method: "POST" });
      onDone();
    } catch (grantError) {
      setError(messageFor(grantError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="text-base font-medium">{CONSENT_PURPOSE}</p>
      <ul className="mt-4 space-y-3 text-base text-muted">
        {CONSENT_POINTS.map((point) => (
          <li key={point} className="flex gap-2.5">
            <span aria-hidden className="text-brand">
              •
            </span>
            <span>{point}</span>
          </li>
        ))}
      </ul>

      {error ? (
        <p role="alert" className="mt-3 text-base font-medium text-red-700 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void grant()}
        disabled={busy}
        className="btn btn-primary mt-5 w-full"
      >
        {busy ? "กำลังบันทึก…" : "ยินยอมและไปต่อ"}
      </button>
      <p className="mt-3 text-center text-sm text-muted">
        ถอนความยินยอมได้ภายหลังที่หน้าข้อมูลสุขภาพ
      </p>
    </>
  );
}
