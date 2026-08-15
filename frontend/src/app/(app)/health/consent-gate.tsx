"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card } from "@/components/ui";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import {
  CONSENT_POINTS,
  CONSENT_PURPOSE,
  CONSENT_WITHDRAW_NOTE,
} from "@/lib/consent-text";
import { formatDate } from "@/lib/format";
import type { Consent } from "@/lib/types";

/**
 * The consent gate, shown before anything else on the health screen.
 *
 * Nothing is pre-ticked and nothing is implied: the member reads what the club wants to
 * hold and presses a button, or they don't. Withdrawing is offered as plainly as
 * granting, because under PDPA it is a right rather than a favour, and burying it would
 * make the original agreement worth less.
 */
export function ConsentGate({ consent }: { consent: Consent | null }) {
  const api = useApi();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = consent?.active === true;
  // Present, not withdrawn, but agreed to wording that has since changed.
  const outdated = consent !== null && !consent.active && consent.withdrawn_at === null;

  async function act(method: "POST" | "DELETE") {
    setError(null);
    setBusy(true);
    try {
      await api<unknown>("/consent", { method });
      router.refresh();
    } catch (actError) {
      setError(messageFor(actError));
    } finally {
      setBusy(false);
    }
  }

  if (active) {
    return (
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium">คุณให้ความยินยอมแล้ว</p>
            <p className="mt-0.5 text-xs text-muted">
              เมื่อ {formatDate(consent.granted_at)} · ฉบับ {consent.version}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void act("DELETE")}
            disabled={busy}
            className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50"
          >
            {busy ? "กำลังดำเนินการ…" : "ถอนความยินยอม"}
          </button>
        </div>
        <p className="mt-3 text-xs text-muted">{CONSENT_WITHDRAW_NOTE}</p>
        {error ? <ErrorText>{error}</ErrorText> : null}
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="font-medium">ขอความยินยอมก่อนบันทึกข้อมูลสุขภาพ</h2>

      {outdated ? (
        <p className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
          ⚠️ ข้อความขอความยินยอมมีการแก้ไขตั้งแต่ครั้งที่คุณตกลงไว้ (ฉบับ {consent.version})
          กรุณาอ่านและยืนยันอีกครั้ง
        </p>
      ) : null}

      <p className="mt-3 text-sm">{CONSENT_PURPOSE}</p>
      <ul className="mt-3 space-y-1.5 text-sm text-muted">
        {CONSENT_POINTS.map((point) => (
          <li key={point} className="flex gap-2">
            <span aria-hidden>•</span>
            <span>{point}</span>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => void act("POST")}
        disabled={busy}
        className="mt-5 w-full rounded-lg bg-brand px-4 py-3 font-medium text-white active:opacity-80 disabled:opacity-50"
      >
        {busy ? "กำลังบันทึก…" : "ยินยอม"}
      </button>
      <p className="mt-2 text-center text-xs text-muted">
        ไม่ยินยอมก็ใช้งานส่วนอื่นของแอปได้ตามปกติ
      </p>
      {error ? <ErrorText>{error}</ErrorText> : null}
    </Card>
  );
}

function ErrorText({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">
      {children}
    </p>
  );
}
