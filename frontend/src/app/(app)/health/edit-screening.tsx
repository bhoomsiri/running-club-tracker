"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ScreeningForm } from "@/components/forms/screening-form";
import { Badge, Card } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { NO_RISK_NOTE, RISK_WARNING } from "@/lib/screening-text";
import type { Screening } from "@/lib/types";

/**
 * The screening after onboarding: a summary the member can reopen.
 *
 * Only the result is shown until they ask to see more — the answers are the sensitive
 * part, and a health page that lists someone's cardiac history the moment it loads is
 * one shoulder-glance away from disclosing it.
 */
export function EditScreening({ screening }: { screening: Screening | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);

  if (open) {
    return (
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <p className="font-medium">แบบคัดกรองก่อนออกกำลังกาย</p>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="text-sm text-muted underline"
          >
            ยกเลิก
          </button>
        </div>
        <ScreeningForm
          initial={screening}
          submitLabel="บันทึกแบบคัดกรอง"
          onSaved={() => {
            setOpen(false);
            router.refresh();
          }}
        />
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">แบบคัดกรองก่อนออกกำลังกาย</p>
          {screening ? (
            <p className="mt-0.5 text-sm text-muted">
              ตอบเมื่อ {formatDate(screening.screened_on)}
            </p>
          ) : (
            <p className="mt-0.5 text-sm text-muted">ยังไม่ได้ทำแบบคัดกรอง</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="shrink-0 rounded-lg border border-border px-3 py-2 text-sm"
        >
          {screening ? "แก้ไข" : "เริ่มทำ"}
        </button>
      </div>

      {screening ? (
        <div className="mt-3">
          {screening.needs_medical_advice ? (
            <>
              <Badge>ควรพบแพทย์</Badge>
              <p className="mt-2 text-sm text-red-700 dark:text-red-300">{RISK_WARNING}</p>
            </>
          ) : (
            <>
              <Badge tone="success">ไม่พบข้อบ่งชี้</Badge>
              <p className="mt-2 text-sm text-muted">{NO_RISK_NOTE}</p>
            </>
          )}
        </div>
      ) : null}
    </Card>
  );
}
