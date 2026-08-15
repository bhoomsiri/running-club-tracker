"use client";

import { useState } from "react";

import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import type { MemberProfile, Sex } from "@/lib/types";

/**
 * The member's own details. Used by the onboarding wizard and by the profile screen, so
 * the rules a member meets are the same wherever they meet them.
 *
 * All six fields together, matching the backend: half an emergency contact is no use to
 * anyone at the roadside, so there is no partial save.
 */

const CURRENT_YEAR = new Date().getFullYear();
const MIN_BIRTH_YEAR = 1900;
const MAX_BIRTH_YEAR = CURRENT_YEAR - 10;

/** Same shape the backend accepts, so a number that passes here is not rejected there. */
const PHONE_RE = /^0\d{8,9}$/;

function normalisePhone(value: string): string {
  return value.replace(/[\s-]/g, "").trim();
}

export function ProfileForm({
  initial,
  submitLabel,
  onSaved,
}: {
  initial: MemberProfile | null;
  submitLabel: string;
  onSaved: () => void;
}) {
  const api = useApi();

  const [fullName, setFullName] = useState(initial?.full_name_th ?? "");
  const [birthYear, setBirthYear] = useState(
    initial?.birth_year ? String(initial.birth_year) : "",
  );
  const [sex, setSex] = useState<Sex | "">(() => initial?.sex ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [contactName, setContactName] = useState(initial?.emergency_contact_name ?? "");
  const [contactPhone, setContactPhone] = useState(
    initial?.emergency_contact_phone ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const yearValue = Number(birthYear);
  const yearOk =
    /^\d{4}$/.test(birthYear) && yearValue >= MIN_BIRTH_YEAR && yearValue <= MAX_BIRTH_YEAR;
  const phoneOk = PHONE_RE.test(normalisePhone(phone));
  const contactPhoneOk = PHONE_RE.test(normalisePhone(contactPhone));

  const canSave =
    fullName.trim() !== "" &&
    yearOk &&
    sex !== "" &&
    phoneOk &&
    contactName.trim() !== "" &&
    contactPhoneOk &&
    !busy;

  async function onSubmit() {
    // `canSave` already proves sex is set, and TypeScript follows that through the
    // alias — so no second check here, which it would flag as unreachable.
    if (!canSave) return;
    setError(null);
    setBusy(true);
    try {
      await api<MemberProfile>("/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name_th: fullName.trim(),
          birth_year: yearValue,
          sex,
          phone: normalisePhone(phone),
          emergency_contact_name: contactName.trim(),
          emergency_contact_phone: normalisePhone(contactPhone),
        }),
      });
      onSaved();
    } catch (saveError) {
      setError(messageFor(saveError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Field label="ชื่อ-นามสกุล (ภาษาไทย)" htmlFor="full-name">
        <input
          id="full-name"
          type="text"
          value={fullName}
          onChange={(event) => setFullName(event.target.value)}
          placeholder="เช่น สมชาย ใจดี"
          autoComplete="name"
          className={inputClass}
        />
      </Field>

      <Field label="ปีเกิด (พ.ศ. หรือ ค.ศ. ก็ได้ ใส่เป็น ค.ศ.)" htmlFor="birth-year">
        <input
          id="birth-year"
          type="text"
          inputMode="numeric"
          value={birthYear}
          onChange={(event) => setBirthYear(event.target.value)}
          placeholder={String(1990)}
          className={inputClass}
        />
        {birthYear !== "" && !yearOk ? (
          <FieldError>
            ใส่ปีเป็น ค.ศ. 4 หลัก ระหว่าง {MIN_BIRTH_YEAR}–{MAX_BIRTH_YEAR}
          </FieldError>
        ) : null}
      </Field>

      <fieldset>
        <legend className="mb-2 text-sm font-medium">เพศ</legend>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              { value: "male", label: "ชาย" },
              { value: "female", label: "หญิง" },
            ] as const
          ).map((option) => (
            <label
              key={option.value}
              className={`cursor-pointer rounded-lg border px-3 py-2.5 text-center text-sm ${
                sex === option.value ? "border-brand bg-brand/10 font-medium" : "border-border"
              }`}
            >
              <input
                type="radio"
                name="sex"
                value={option.value}
                checked={sex === option.value}
                onChange={() => setSex(option.value)}
                className="sr-only"
              />
              {option.label}
            </label>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-muted">
          ใช้ประกอบการประเมินความเสี่ยงในการออกกำลังกายเท่านั้น
        </p>
      </fieldset>

      <Field label="เบอร์โทรของคุณ" htmlFor="phone">
        <input
          id="phone"
          type="tel"
          inputMode="tel"
          value={phone}
          onChange={(event) => setPhone(event.target.value)}
          placeholder="0812345678"
          autoComplete="tel"
          className={inputClass}
        />
        {phone !== "" && !phoneOk ? <FieldError>{PHONE_HINT}</FieldError> : null}
      </Field>

      <div className="rounded-xl border border-border p-3">
        <p className="text-sm font-medium">ผู้ติดต่อกรณีฉุกเฉิน</p>
        <p className="mt-0.5 mb-3 text-xs text-muted">
          คนที่ชมรมจะติดต่อได้ทันทีหากเกิดเหตุระหว่างกิจกรรม
        </p>

        <Field label="ชื่อผู้ติดต่อ" htmlFor="contact-name">
          <input
            id="contact-name"
            type="text"
            value={contactName}
            onChange={(event) => setContactName(event.target.value)}
            placeholder="เช่น สมหญิง ใจดี"
            className={inputClass}
          />
        </Field>

        <div className="mt-3">
          <Field label="เบอร์ผู้ติดต่อ" htmlFor="contact-phone">
            <input
              id="contact-phone"
              type="tel"
              inputMode="tel"
              value={contactPhone}
              onChange={(event) => setContactPhone(event.target.value)}
              placeholder="0898765432"
              className={inputClass}
            />
            {contactPhone !== "" && !contactPhoneOk ? (
              <FieldError>{PHONE_HINT}</FieldError>
            ) : null}
          </Field>
        </div>
      </div>

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

const PHONE_HINT = "ใส่เบอร์ในประเทศไทย ขึ้นต้นด้วย 0 เช่น 0812345678";

const inputClass =
  "w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base outline-none focus:border-brand";

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}

function FieldError({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-red-600 dark:text-red-400">{children}</p>;
}
