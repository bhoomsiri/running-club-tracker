"use client";

import { useState } from "react";

import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { todayLocal } from "@/lib/run-form";
import {
  NO_RISK_NOTE,
  RISK_ACKNOWLEDGEMENT,
  RISK_WARNING,
  SCREENING_ALL_KEYS,
  SCREENING_SECTIONS,
} from "@/lib/screening-text";
import type { Screening } from "@/lib/types";

/**
 * The PAR-Q+ questions.
 *
 * Every question starts unanswered rather than defaulting to "no". A pre-ticked "no" on
 * a cardiac question is an answer nobody gave, and reading it as a clean result is the
 * one failure this form exists to prevent — so the save button stays disabled until all
 * eleven have been chosen, and the backend refuses a partial set as well.
 *
 * A "yes" warns; it never blocks. The club is not a doctor's surgery, and eleven
 * checkboxes are not a diagnosis.
 */
export function ScreeningForm({
  initial,
  submitLabel,
  onSaved,
}: {
  initial: Screening | null;
  submitLabel: string;
  onSaved: () => void;
}) {
  const api = useApi();

  const [answers, setAnswers] = useState<Record<string, boolean>>(
    () => initial?.answers ?? {},
  );
  const [acknowledged, setAcknowledged] = useState(initial?.risk_acknowledged ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answered = SCREENING_ALL_KEYS.filter((key) => key in answers);
  const allAnswered = answered.length === SCREENING_ALL_KEYS.length;
  const anyYes = Object.values(answers).some(Boolean);

  async function onSubmit() {
    if (!allAnswered || !acknowledged) return;
    setError(null);
    setBusy(true);
    try {
      await api<Screening>("/screening", {
        method: "POST",
        body: JSON.stringify({
          answers,
          risk_acknowledged: acknowledged,
          screened_on: todayLocal(),
        }),
      });
      onSaved();
    } catch (saveError) {
      setError(
        saveError instanceof ApiError && saveError.status === 403
          ? "ต้องให้ความยินยอมก่อนจึงจะบันทึกแบบคัดกรองได้"
          : messageFor(saveError),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {SCREENING_SECTIONS.map((section) => (
        <section key={section.title}>
          <h3 className="text-sm font-semibold">{section.title}</h3>
          <p className="mt-0.5 mb-3 text-xs text-muted">{section.hint}</p>

          <ul className="space-y-3">
            {section.questions.map((question) => (
              <li key={question.key} className="rounded-lg border border-border p-3">
                <p className="text-sm">{question.text}</p>
                <div className="mt-2.5 grid grid-cols-2 gap-2">
                  {(
                    [
                      { value: true, label: "ใช่" },
                      { value: false, label: "ไม่ใช่" },
                    ] as const
                  ).map((option) => {
                    const selected = answers[question.key] === option.value;
                    return (
                      <label
                        key={String(option.value)}
                        className={`cursor-pointer rounded-lg border px-3 py-2 text-center text-sm ${
                          selected
                            ? option.value
                              ? "border-amber-500 bg-amber-500/15 font-medium"
                              : "border-brand bg-brand/10 font-medium"
                            : "border-border"
                        }`}
                      >
                        <input
                          type="radio"
                          name={question.key}
                          checked={selected}
                          onChange={() =>
                            setAnswers((current) => ({
                              ...current,
                              [question.key]: option.value,
                            }))
                          }
                          className="sr-only"
                        />
                        {option.label}
                      </label>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <p className="text-sm text-muted">
        ตอบแล้ว {answered.length} จาก {SCREENING_ALL_KEYS.length} ข้อ
      </p>

      {allAnswered ? (
        anyYes ? (
          <p
            role="status"
            className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-3 text-sm text-red-800 dark:text-red-200"
          >
            ⚠️ {RISK_WARNING}
          </p>
        ) : (
          <p
            role="status"
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-3 text-sm text-emerald-800 dark:text-emerald-200"
          >
            ✅ {NO_RISK_NOTE}
          </p>
        )
      ) : null}

      <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
          className="mt-1 shrink-0"
        />
        <span className="text-sm text-muted">{RISK_ACKNOWLEDGEMENT}</span>
      </label>

      {error ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void onSubmit()}
        disabled={!allAnswered || !acknowledged || busy}
        className="w-full rounded-lg bg-brand px-4 py-3.5 font-medium text-white active:opacity-80 disabled:opacity-40"
      >
        {busy ? "กำลังบันทึก…" : submitLabel}
      </button>
      {!allAnswered ? (
        <p className="text-center text-xs text-muted">กรุณาตอบให้ครบทุกข้อก่อน</p>
      ) : null}
    </div>
  );
}
