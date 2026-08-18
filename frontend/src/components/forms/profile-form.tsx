"use client";

import { useState } from "react";

import { SearchableSelect } from "@/components/forms/searchable-select";
import { ShirtSizeField } from "@/components/forms/shirt-size-field";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { DEPARTMENTS, POSITIONS } from "@/lib/roster-options";
import type { MemberProfile, Sex, ShirtSize } from "@/lib/types";

/**
 * The member's own details. Used by the onboarding wizard and by the profile screen, so
 * the rules a member meets are the same wherever they meet them.
 *
 * Every field together, matching the backend: half an emergency contact is no use to
 * anyone at the roadside, so there is no partial save.
 *
 * Job and unit are picked from the hospital's own lists, with "อื่นๆ (ระบุเอง)" for
 * anyone the lists have missed — typing a unit freehand produced five spellings of the
 * same ward. The field itself is still free text end to end: what is typed under "อื่นๆ"
 * is saved as typed, and the list only grows when lib/roster-options.ts is edited.
 */

const CURRENT_YEAR = new Date().getFullYear();
const MIN_BIRTH_YEAR = 1900;
const MAX_BIRTH_YEAR = CURRENT_YEAR - 10;
/** A four-digit year above this is a พ.ศ. year typed where ค.ศ. was asked for — the
 * commonest mistake on this form, and one that fails validation with no clue why. */
const LOOKS_BUDDHIST_ABOVE = 2200;
const BUDDHIST_OFFSET = 543;

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
  const [position, setPosition] = useState(initial?.position ?? "");
  const [department, setDepartment] = useState(initial?.department ?? "");
  const [shirtSize, setShirtSize] = useState<ShirtSize | "">(initial?.shirt_size ?? "");
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
  const looksBuddhist = /^\d{4}$/.test(birthYear) && yearValue > LOOKS_BUDDHIST_ABOVE;
  const phoneOk = PHONE_RE.test(normalisePhone(phone));
  const contactPhoneOk = PHONE_RE.test(normalisePhone(contactPhone));

  const canSave =
    fullName.trim() !== "" &&
    yearOk &&
    sex !== "" &&
    position.trim() !== "" &&
    department.trim() !== "" &&
    shirtSize !== "" &&
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
          position: position.trim(),
          department: department.trim(),
          shirt_size: shirtSize,
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

      <Field label="ปีเกิด (ค.ศ.)" htmlFor="birth-year">
        <input
          id="birth-year"
          type="text"
          inputMode="numeric"
          value={birthYear}
          onChange={(event) => setBirthYear(event.target.value)}
          placeholder="1990"
          className={inputClass}
        />
        <p className="mt-2 text-sm text-muted">
          กรอกเป็น ค.ศ. เช่น 1990 (พ.ศ. − {BUDDHIST_OFFSET} = ค.ศ.)
        </p>
        {/* A wrong-era year is the mistake this form gets, so it is answered with the
            arithmetic already done rather than with the range it failed. */}
        {looksBuddhist ? (
          <FieldError>
            กรุณากรอกเป็น ค.ศ. — พ.ศ. {yearValue} คือ ค.ศ. {yearValue - BUDDHIST_OFFSET}
          </FieldError>
        ) : birthYear !== "" && !yearOk ? (
          <FieldError>
            ใส่ปีเป็น ค.ศ. 4 หลัก ระหว่าง {MIN_BIRTH_YEAR}–{MAX_BIRTH_YEAR}
          </FieldError>
        ) : null}
      </Field>

      <fieldset>
        <legend className="mb-2 text-base font-semibold">เพศ</legend>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              { value: "male", label: "ชาย" },
              { value: "female", label: "หญิง" },
            ] as const
          ).map((option) => (
            <label
              key={option.value}
              className={`flex min-h-12 cursor-pointer items-center justify-center rounded-control border px-3 text-center text-base ${
                sex === option.value
                  ? "border-brand bg-brand-tint font-semibold"
                  : "border-border"
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
        <p className="mt-2 text-sm text-muted">
          ใช้ประกอบการประเมินความเสี่ยงในการออกกำลังกายเท่านั้น
        </p>
      </fieldset>

      <SearchableSelect
        id="position"
        label="ตำแหน่ง"
        options={POSITIONS}
        value={position}
        onChange={setPosition}
        placeholder="เลือกตำแหน่ง"
        otherPlaceholder="พิมพ์ตำแหน่งของคุณ"
      />

      <SearchableSelect
        id="department"
        label="หน่วยงาน / กลุ่มงาน"
        options={DEPARTMENTS}
        value={department}
        onChange={setDepartment}
        placeholder="เลือกหน่วยงาน"
        otherPlaceholder="พิมพ์ชื่อหน่วยงานของคุณ"
        hint="ใช้จัดกลุ่มผู้เข้าร่วมและสรุปผลกลับไปยังหน่วยงาน"
      />

      <ShirtSizeField value={shirtSize} onChange={setShirtSize} />

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

      <div className="rounded-card border border-border p-4">
        <p className="text-sm font-medium">ผู้ติดต่อกรณีฉุกเฉิน</p>
        <p className="mt-1 mb-4 text-sm text-muted">
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
        <p role="alert" className="text-base font-medium text-red-700 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void onSubmit()}
        disabled={!canSave}
        className="btn btn-primary w-full"
      >
        {busy ? "กำลังบันทึก…" : submitLabel}
      </button>
    </div>
  );
}

const PHONE_HINT = "ใส่เบอร์ในประเทศไทย ขึ้นต้นด้วย 0 เช่น 0812345678";

const inputClass = "input-field";

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
      <label htmlFor={htmlFor} className="mb-2 block text-base font-semibold">
        {label}
      </label>
      {children}
    </div>
  );
}

function FieldError({ children }: { children: React.ReactNode }) {
  return <p className="mt-2 text-sm font-medium text-red-700 dark:text-red-400">{children}</p>;
}
