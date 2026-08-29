"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Badge, Button, Card } from "@/components/ui";
import { useApi } from "@/lib/api-client";
import {
  fromDurationSeconds,
  isValidDistance,
  MAX_CALORIES_BURNED,
  MAX_STEPS,
  parseOptionalCount,
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
 *
 * Laid out as two numbered steps with only one of them live at a time. Showing the empty
 * distance and duration fields before there is a photo to read them from invites people
 * to fill the form in by hand and then wonder why it changed under them.
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
  // Optional, and kept as strings like every other field here: "" is the member leaving
  // the box alone, which is a different thing from a zero.
  const [calories, setCalories] = useState("");
  const [steps, setSteps] = useState("");

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
    // Most screenshots carry neither, so a null here is the ordinary case rather than a
    // failure — the box simply stays empty for the member to fill in or ignore.
    if (result.draft.calories_burned !== null) {
      setCalories(String(result.draft.calories_burned));
    }
    if (result.draft.steps !== null) setSteps(String(result.draft.steps));

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
  const caloriesValue = parseOptionalCount(calories, MAX_CALORIES_BURNED);
  const stepsValue = parseOptionalCount(steps, MAX_STEPS);
  const canSubmit =
    imageKey !== null &&
    isValidDistance(distance) &&
    durationSeconds !== null &&
    runDate !== "" &&
    // Empty is fine; wrong is not. Letting a bad value through would trade a message
    // beside the field for a 422 after the button.
    caloriesValue !== "invalid" &&
    stepsValue !== "invalid" &&
    stage === "form";

  async function onConfirm() {
    // Guarding on canSubmit is also what narrows caloriesValue and stepsValue to
    // `number | null` below — TypeScript follows the aliased condition, so neither needs
    // re-checking here and neither is cast.
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
          // null, not omitted: the member left it blank and the backend stores that as
          // "not recorded". Both are already validated to be a number or null here.
          calories_burned: caloriesValue,
          steps: stepsValue,
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
          className="rounded-card border border-red-600/40 bg-red-600/10 px-4 py-3.5 text-base font-medium text-red-800 dark:text-red-300"
        >
          {error}
        </p>
      ) : null}

      <Card>
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">
            <span className="text-muted">1.</span> รูปหลักฐาน
          </h2>
          {imageKey ? <Badge tone="success">อัปโหลดแล้ว</Badge> : null}
        </div>

        {previewUrl ? (
          <div className="relative mt-4 h-56 w-full overflow-hidden rounded-control bg-border">
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

        <label className="mt-4 block">
          <span className="sr-only">เลือกรูปหลักฐาน</span>
          {/* No `capture`: it forces the camera open and takes the gallery away, and
              most members screenshot their run first and send it later. Without it the
              phone offers both. */}
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              // Cleared so choosing the same file again still fires a change event.
              event.target.value = "";
              if (file) void onFileChosen(file);
            }}
            className="block w-full text-base text-muted file:mr-4 file:min-h-12 file:rounded-control file:border-0 file:bg-brand file:px-5 file:font-semibold file:text-on-brand disabled:opacity-50"
          />
        </label>
        <p className="mt-3 text-sm text-muted">
          แคปหน้าจอจากแอปวิ่ง หรือถ่ายรูปหน้าจอลู่วิ่งก็ได้ — รองรับ jpg, png, webp ไม่เกิน 10 MB
        </p>

        {stage === "uploading" ? <Progress>กำลังอัปโหลดรูป…</Progress> : null}
        {stage === "extracting" ? <Progress>กำลังให้ระบบอ่านค่าจากรูป…</Progress> : null}
      </Card>

      {stage === "form" || stage === "saving" ? (
        <Card>
          <h2 className="text-lg font-semibold">
            <span className="text-muted">2.</span> ตรวจสอบและยืนยัน
          </h2>

          {notice ? (
            <p className="mt-4 rounded-control border border-amber-500/50 bg-amber-500/15 px-4 py-3 text-base font-medium text-amber-900 dark:text-amber-200">
              ⚠️ {notice}
            </p>
          ) : null}

          <p className="mt-3 text-sm text-muted">
            ตัวเลขที่ระบบอ่านมาเป็นเพียงค่าตั้งต้น กรุณาตรวจสอบและแก้ให้ตรงกับที่วิ่งจริงก่อนกดยืนยัน
          </p>

          <div className="mt-5 space-y-5">
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
                  className={`${inputClass} text-center text-lg`}
                />
                <span className="shrink-0 text-base text-muted">นาที</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={seconds}
                  onChange={(event) => setSeconds(event.target.value)}
                  placeholder="00"
                  aria-label="วินาที"
                  className={`${inputClass} text-center text-lg`}
                />
                <span className="shrink-0 text-base text-muted">วินาที</span>
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
              <p className="mt-2 text-sm text-muted">
                กิจกรรมวันละ 10 กม. นับเฉพาะที่ส่งภายในวันถัดไป
              </p>
            </Field>

            <fieldset className="border-t border-border pt-5">
              <legend className="text-base font-semibold">
                แคลอรี่และจำนวนก้าว{" "}
                <span className="font-medium text-muted">(ไม่บังคับ)</span>
              </legend>
              <p className="mt-1 mb-3 text-sm text-muted">
                ถ้าแอปวิ่งของคุณแสดงไว้ ระบบจะกรอกให้เอง — ไม่มีก็ข้ามได้ ไม่มีผลกับระยะสะสมหรือแต้ม
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="แคลอรี่ (kcal)" htmlFor="calories">
                  <input
                    id="calories"
                    type="text"
                    inputMode="numeric"
                    value={calories}
                    onChange={(event) => setCalories(event.target.value)}
                    placeholder="ไม่ระบุ"
                    className={inputClass}
                  />
                  {caloriesValue === "invalid" ? (
                    <FieldError>
                      ใส่จำนวนเต็มระหว่าง 1 ถึง {(MAX_CALORIES_BURNED - 1).toLocaleString()}{" "}
                      หรือเว้นว่างไว้
                    </FieldError>
                  ) : null}
                </Field>

                <Field label="จำนวนก้าว" htmlFor="steps">
                  <input
                    id="steps"
                    type="text"
                    inputMode="numeric"
                    value={steps}
                    onChange={(event) => setSteps(event.target.value)}
                    placeholder="ไม่ระบุ"
                    className={inputClass}
                  />
                  {stepsValue === "invalid" ? (
                    <FieldError>
                      ใส่จำนวนเต็มระหว่าง 1 ถึง {(MAX_STEPS - 1).toLocaleString()} หรือเว้นว่างไว้
                    </FieldError>
                  ) : null}
                </Field>
              </div>
            </fieldset>

            <fieldset>
              <legend className="mb-2 text-base font-semibold">ที่มาของรูป</legend>
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

          <Button onClick={() => void onConfirm()} disabled={!canSubmit} className="mt-6">
            {stage === "saving" ? "กำลังบันทึก…" : "ยืนยันและบันทึก"}
          </Button>
        </Card>
      ) : null}
    </div>
  );
}

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
  return (
    <p className="mt-2 text-sm font-medium text-red-700 dark:text-red-400">{children}</p>
  );
}

function Progress({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="mt-4 flex items-center gap-3 rounded-control bg-brand-tint px-4 py-3 text-base font-medium text-brand"
      aria-live="polite"
    >
      <span className="h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-brand/30 border-t-brand" />
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
      className={`flex min-h-12 cursor-pointer items-center gap-3 rounded-control border px-4 py-3 ${
        selected ? "border-brand bg-brand-tint" : "border-border"
      }`}
    >
      <input
        type="radio"
        name="source"
        value={value}
        checked={selected}
        onChange={() => onSelect(value)}
        className="h-5 w-5 shrink-0"
      />
      <span>
        <span className="block text-base font-semibold">{label}</span>
        <span className="block text-sm text-muted">{hint}</span>
      </span>
    </label>
  );
}
