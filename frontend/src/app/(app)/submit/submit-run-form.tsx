"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Badge, Card } from "@/components/ui";
import { useApi } from "@/lib/api-client";
import {
  fromDurationSeconds,
  isValidDistance,
  todayLocal,
  toDurationSeconds,
} from "@/lib/run-form";
import {
  extractionNotice,
  submitErrorMessage,
  uploadErrorMessage,
} from "@/lib/submit-errors";
import type { EvidenceUpload, ExtractResult, Run, RunSource } from "@/lib/types";

/**
 * Upload → read → confirm.
 *
 * The middle step only ever fills the form in. What gets saved is what the member sees
 * on screen and presses the button for, which is the whole reason the AI's answer is
 * called a draft: it can be wrong, and the person who ran is the one who knows.
 */

/** Below this the reading is offered with a warning rather than presented as fact. */
const LOW_CONFIDENCE = 0.7;

type Stage = "choose" | "uploading" | "extracting" | "form" | "saving";

export function SubmitRunForm() {
  const api = useApi();
  const router = useRouter();

  const [stage, setStage] = useState<Stage>("choose");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageKey, setImageKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [distance, setDistance] = useState("");
  const [minutes, setMinutes] = useState("");
  const [seconds, setSeconds] = useState("");
  const [runDate, setRunDate] = useState(todayLocal);
  const [source, setSource] = useState<RunSource>("app_screenshot");

  // Object URLs are held by the browser until they are revoked; without this every
  // retry leaks the previous image.
  const objectUrl = useRef<string | null>(null);
  useEffect(() => {
    return () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    };
  }, []);

  async function onFileChosen(file: File) {
    setError(null);
    setNotice(null);

    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(file);
    setPreviewUrl(objectUrl.current);

    setStage("uploading");
    let uploaded: EvidenceUpload;
    try {
      const body = new FormData();
      body.append("file", file);
      uploaded = await api<EvidenceUpload>("/runs/evidence", { method: "POST", body });
      setImageKey(uploaded.image_key);
    } catch (uploadError) {
      setError(uploadErrorMessage(uploadError));
      setStage("choose");
      return;
    }

    // From here the member can always finish by hand, so nothing below is allowed to
    // send them back to the start.
    setStage("extracting");
    try {
      const result = await api<ExtractResult>("/runs/extract", {
        method: "POST",
        body: JSON.stringify({ image_key: uploaded.image_key }),
      });
      applyDraft(result);
    } catch (extractError) {
      setNotice(extractionNotice(extractError));
    }
    setStage("form");
  }

  function applyDraft(result: ExtractResult) {
    // Each field is filled only if it was actually read. A null is the extractor saying
    // it could not tell — filling in a zero would turn "unknown" into a number the
    // member might not look at twice.
    if (result.draft.distance_km !== null) setDistance(result.draft.distance_km);
    if (result.draft.duration_seconds !== null) {
      const { minutes: m, seconds: s } = fromDurationSeconds(result.draft.duration_seconds);
      setMinutes(m);
      setSeconds(s);
    }
    if (result.draft.run_date !== null) setRunDate(result.draft.run_date);

    const unsure =
      Number(result.confidence) < LOW_CONFIDENCE || result.warnings.length > 0;
    setNotice(
      unsure
        ? `ระบบอ่านค่าได้ไม่ชัดเจน โปรดตรวจสอบตัวเลขก่อนยืนยัน${
            result.warnings.length > 0 ? ` (${result.warnings.join(", ")})` : ""
          }`
        : null,
    );
  }

  const durationSeconds = toDurationSeconds(minutes, seconds);
  const canSubmit =
    imageKey !== null &&
    isValidDistance(distance) &&
    durationSeconds !== null &&
    runDate !== "" &&
    stage === "form";

  async function onConfirm() {
    if (!canSubmit || imageKey === null || durationSeconds === null) return;
    setError(null);
    setStage("saving");
    try {
      await api<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({
          // A string, deliberately: the backend stores it as a Decimal and this is the
          // last place a float could quietly round it.
          distance_km: distance.trim(),
          duration_seconds: durationSeconds,
          run_date: runDate,
          image_key: imageKey,
          source,
        }),
      });
      // refresh() so the dashboard re-renders on the server with the new totals rather
      // than showing a cached page that has not caught up.
      router.push("/dashboard");
      router.refresh();
    } catch (submitError) {
      setError(submitErrorMessage(submitError));
      setStage("form");
    }
  }

  const busy = stage === "uploading" || stage === "extracting" || stage === "saving";

  return (
    <div className="space-y-4">
      {error ? (
        <p
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300"
        >
          {error}
        </p>
      ) : null}

      <Card>
        <div className="flex items-center justify-between">
          <h2 className="font-medium">1. รูปหลักฐาน</h2>
          {imageKey ? <Badge tone="success">อัปโหลดแล้ว</Badge> : null}
        </div>

        {previewUrl ? (
          <div className="relative mt-3 h-56 w-full overflow-hidden rounded-lg bg-border">
            {/* A local blob URL, so Next's optimiser has nothing to fetch. */}
            <Image
              src={previewUrl}
              alt="รูปหลักฐานการวิ่ง"
              fill
              unoptimized
              className="object-contain"
            />
          </div>
        ) : null}

        <label className="mt-3 block">
          <span className="sr-only">เลือกรูปหลักฐาน</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              // Cleared so choosing the same file again still fires a change event.
              event.target.value = "";
              if (file) void onFileChosen(file);
            }}
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-4 file:py-2.5 file:text-white disabled:opacity-50"
          />
        </label>
        <p className="mt-2 text-xs text-muted">
          แคปหน้าจอจากแอปวิ่ง หรือถ่ายรูปหน้าจอลู่วิ่งก็ได้ — รองรับ jpg, png, webp ไม่เกิน 10 MB
        </p>

        {stage === "uploading" ? <Progress>กำลังอัปโหลดรูป…</Progress> : null}
        {stage === "extracting" ? <Progress>กำลังให้ระบบอ่านค่าจากรูป…</Progress> : null}
      </Card>

      {stage === "form" || stage === "saving" ? (
        <Card>
          <h2 className="font-medium">2. ตรวจสอบและยืนยัน</h2>

          {notice ? (
            <p className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
              ⚠️ {notice}
            </p>
          ) : null}

          <p className="mt-3 text-xs text-muted">
            ตัวเลขที่ระบบอ่านมาเป็นเพียงค่าตั้งต้น กรุณาตรวจสอบและแก้ให้ตรงกับที่วิ่งจริงก่อนกดยืนยัน
          </p>

          <div className="mt-4 space-y-4">
            <Field label="ระยะทาง (กม.)" htmlFor="distance">
              <input
                id="distance"
                type="text"
                inputMode="decimal"
                value={distance}
                onChange={(event) => setDistance(event.target.value)}
                placeholder="10.50"
                className={inputClass}
              />
              {distance !== "" && !isValidDistance(distance) ? (
                <FieldError>ใส่ตัวเลข เช่น 10 หรือ 10.5 (ทศนิยมไม่เกิน 2 ตำแหน่ง)</FieldError>
              ) : null}
            </Field>

            <Field label="เวลาที่ใช้" htmlFor="minutes">
              <div className="flex items-center gap-2">
                <input
                  id="minutes"
                  type="text"
                  inputMode="numeric"
                  value={minutes}
                  onChange={(event) => setMinutes(event.target.value)}
                  placeholder="60"
                  aria-label="นาที"
                  className={`${inputClass} text-center`}
                />
                <span className="text-muted">นาที</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={seconds}
                  onChange={(event) => setSeconds(event.target.value)}
                  placeholder="00"
                  aria-label="วินาที"
                  className={`${inputClass} text-center`}
                />
                <span className="text-muted">วินาที</span>
              </div>
              {minutes !== "" && durationSeconds === null ? (
                <FieldError>ใส่นาทีเป็นจำนวนเต็ม และวินาที 0–59</FieldError>
              ) : null}
            </Field>

            <Field label="วันที่วิ่ง" htmlFor="run-date">
              <input
                id="run-date"
                type="date"
                value={runDate}
                max={todayLocal()}
                onChange={(event) => setRunDate(event.target.value)}
                className={inputClass}
              />
              <p className="mt-1 text-xs text-muted">
                กิจกรรมวันละ 10 กม. นับเฉพาะที่ส่งภายในวันถัดไป
              </p>
            </Field>

            <fieldset>
              <legend className="mb-2 text-sm font-medium">ที่มาของรูป</legend>
              <div className="grid gap-2">
                <SourceOption
                  value="app_screenshot"
                  current={source}
                  onSelect={setSource}
                  label="แคปจากแอปวิ่ง"
                  hint="Strava, Nike Run Club, Garmin ฯลฯ"
                />
                <SourceOption
                  value="manual_photo"
                  current={source}
                  onSelect={setSource}
                  label="ถ่ายรูปเอง"
                  hint="เช่น หน้าจอลู่วิ่ง หรือนาฬิกา"
                />
              </div>
            </fieldset>
          </div>

          <button
            type="button"
            onClick={() => void onConfirm()}
            disabled={!canSubmit}
            className="mt-6 w-full rounded-lg bg-brand px-4 py-3.5 font-medium text-white active:opacity-80 disabled:opacity-40"
          >
            {stage === "saving" ? "กำลังบันทึก…" : "ยืนยันและบันทึก"}
          </button>
        </Card>
      ) : null}
    </div>
  );
}

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

function Progress({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 flex items-center gap-2 text-sm text-muted" aria-live="polite">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-brand" />
      {children}
    </p>
  );
}

function SourceOption({
  value,
  current,
  onSelect,
  label,
  hint,
}: {
  value: RunSource;
  current: RunSource;
  onSelect: (value: RunSource) => void;
  label: string;
  hint: string;
}) {
  const selected = current === value;
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 ${
        selected ? "border-brand bg-brand/10" : "border-border"
      }`}
    >
      <input
        type="radio"
        name="source"
        value={value}
        checked={selected}
        onChange={() => onSelect(value)}
        className="mt-1"
      />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        <span className="block text-xs text-muted">{hint}</span>
      </span>
    </label>
  );
}
