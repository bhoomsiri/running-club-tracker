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

/** The same bounds `build_profile` enforces, so a date this form accepts is not then
 * refused by the API. `max` and `min` also stop the picker offering an impossible day. */
const MIN_AGE_YEARS = 10;
const EARLIEST_BIRTH_DATE = "1900-01-01";

/** Same shape the backend accepts, so a number that passes here is not rejected there. */
const PHONE_RE = /^0\d{8,9}$/;

function normalisePhone(value: string): string {
  return value.replace(/[\s-]/g, "").trim();
}

/** Today, and the latest birth date that clears the club's minimum age — both as the
 * `YYYY-MM-DD` a date input speaks. Computed in the browser's own zone, which for
 * everyone here is Bangkok's, so "today" means the day they are looking at. */
function isoDate(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function latestAllowedBirthDate(): string {
  const today = new Date();
  return isoDate(
    new Date(today.getFullYear() - MIN_AGE_YEARS, today.getMonth(), today.getDate()),
  );
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
  // Already `YYYY-MM-DD` on the wire, which is exactly what a date input wants — no
  // parsing, no Date object, no timezone to get wrong on the way in or out.
  const [birthDate, setBirthDate] = useState(initial?.birth_date ?? "");
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

  const oldEnoughBy = latestAllowedBirthDate();
  // String comparison, not date arithmetic: ISO dates sort correctly as text, and the
  // value never leaves that form on its way to the API.
  const birthDateOk =
    birthDate >= EARLIEST_BIRTH_DATE && birthDate <= oldEnoughBy && birthDate !== "";
  const tooYoung = birthDate !== "" && birthDate > oldEnoughBy;
  const phoneOk = PHONE_RE.test(normalisePhone(phone));
  const contactPhoneOk = PHONE_RE.test(normalisePhone(contactPhone));

  const canSave =
    fullName.trim() !== "" &&
    birthDateOk &&
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
          birth_date: birthDate,
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

      {/* A date picker rather than a year box, which is what finally settles the พ.ศ.
          problem: there is no number to type in the wrong era. The phone's own calendar
          may well *display* Buddhist years — that is the member's locale, and it is
          right for them — while the value this input holds is always ISO ค.ศ., which is
          exactly what goes to the API. */}
      <Field label="วันเกิด" htmlFor="birth-date">
        <input
          id="birth-date"
          type="date"
          value={birthDate}
          onChange={(event) => setBirthDate(event.target.value)}
          min={EARLIEST_BIRTH_DATE}
          max={oldEnoughBy}
          autoComplete="bday"
          className={inputClass}
        />
        {tooYoung ? (
          <FieldError>ผู้เข้าร่วมต้องมีอายุอย่างน้อย {MIN_AGE_YEARS} ปี</FieldError>
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
