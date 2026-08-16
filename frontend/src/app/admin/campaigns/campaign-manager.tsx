"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Card, EmptyState } from "@/components/ui";
import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDate } from "@/lib/format";
import type { Campaign } from "@/lib/types";

/**
 * Campaigns, and the config each type needs.
 *
 * The config fields are not free-form because they are not free-form to the backend:
 * each campaign type's policy reads specific keys, and a typo in one would not fail
 * loudly — it would change what everyone's points are worth. So the form asks for the
 * keys that type actually uses, and says plainly that changing them recalculates.
 *
 * Editing a running campaign is allowed, because a mistake in a running campaign has to
 * be fixable. It is not quiet: points are reconciled against the policy, so a changed
 * target moves every member's total the next time anything touches their ledger.
 */

type FieldSpec = { key: string; label: string; hint: string };

const CONFIG_FIELDS: Record<string, FieldSpec[]> = {
  cumulative_distance: [
    { key: "target_km", label: "ระยะเป้าหมาย (กม.)", hint: "เช่น 100" },
  ],
  daily_threshold_reward: [
    { key: "qualifying_km", label: "ระยะขั้นต่ำต่อวัน (กม.)", hint: "เช่น 10" },
    { key: "points_per_qualifying_day", label: "แต้มต่อวันที่ผ่านเกณฑ์", hint: "เช่น 1" },
    { key: "submit_within_days", label: "ต้องส่งภายในกี่วัน", hint: "เช่น 1" },
  ],
};

const TYPE_LABELS: Record<string, string> = {
  cumulative_distance: "สะสมระยะรวม",
  daily_threshold_reward: "สะสมแต้มจากวันที่ผ่านเกณฑ์",
};

export function CampaignManager({ campaigns }: { campaigns: Campaign[] }) {
  const [creating, setCreating] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setCreating((open) => !open)}
          className="btn btn-secondary"
        >
          {creating ? "ยกเลิก" : "+ สร้างกิจกรรม"}
        </button>
      </div>

      {creating ? (
        <Card>
          <p className="mb-3 text-lg font-semibold">สร้างกิจกรรมใหม่</p>
          <CampaignForm onDone={() => setCreating(false)} />
        </Card>
      ) : null}

      {campaigns.length === 0 ? (
        <EmptyState>ยังไม่มีกิจกรรม</EmptyState>
      ) : (
        <ul className="space-y-3">
          {campaigns.map((campaign) => (
            <li key={campaign.id}>
              <CampaignRow campaign={campaign} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CampaignRow({ campaign }: { campaign: Campaign }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <p className="text-lg font-semibold">แก้ไข {campaign.name}</p>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-base text-muted underline"
          >
            ยกเลิก
          </button>
        </div>
        <CampaignForm campaign={campaign} onDone={() => setEditing(false)} />
      </Card>
    );
  }

  return (
    <Card className={campaign.is_active ? "" : "opacity-60"}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold">{campaign.name}</span>
            <Badge tone="brand">{TYPE_LABELS[campaign.type] ?? campaign.type}</Badge>
            {campaign.is_active ? null : <Badge>ปิดแล้ว</Badge>}
          </div>
          <p className="mt-0.5 text-sm text-muted">
            {campaign.code} · {formatDate(campaign.starts_on)} –{" "}
            {formatDate(campaign.ends_on)}
          </p>
          <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted tabular-nums">
            {(CONFIG_FIELDS[campaign.type] ?? []).map((field) => (
              <div key={field.key} className="flex gap-1">
                <dt>{field.label}</dt>
                <dd className="text-lg font-semibold">{String(campaign.config[field.key] ?? "—")}</dd>
              </div>
            ))}
          </dl>
        </div>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="btn btn-secondary shrink-0"
        >
          แก้ไข
        </button>
      </div>
    </Card>
  );
}

function CampaignForm({
  campaign,
  onDone,
}: {
  campaign?: Campaign;
  onDone: () => void;
}) {
  const api = useApi();
  const router = useRouter();

  const [code, setCode] = useState(campaign?.code ?? "");
  const [name, setName] = useState(campaign?.name ?? "");
  const [type, setType] = useState(campaign?.type ?? "cumulative_distance");
  const [startsOn, setStartsOn] = useState(campaign?.starts_on ?? "");
  const [endsOn, setEndsOn] = useState(campaign?.ends_on ?? "");
  const [active, setActive] = useState(campaign?.is_active ?? true);
  const [config, setConfig] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      (CONFIG_FIELDS[campaign?.type ?? "cumulative_distance"] ?? []).map((field) => [
        field.key,
        String(campaign?.config[field.key] ?? ""),
      ]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fields = CONFIG_FIELDS[type] ?? [];
  const configOk = fields.every((field) => /^\d{1,5}$/.test((config[field.key] ?? "").trim()));
  const datesOk = startsOn !== "" && endsOn !== "" && startsOn <= endsOn;
  const canSave =
    name.trim() !== "" && (campaign || code.trim() !== "") && datesOk && configOk && !busy;

  async function save() {
    if (!canSave) return;
    setError(null);
    setBusy(true);
    // The policy reads these as numbers; the form collects whole numbers only, so this
    // conversion cannot lose anything a member is owed.
    const parsedConfig = Object.fromEntries(
      fields.map((field) => [field.key, Number((config[field.key] ?? "").trim())]),
    );

    try {
      if (campaign) {
        await api<Campaign>(`/admin/campaigns/${campaign.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: name.trim(),
            starts_on: startsOn,
            ends_on: endsOn,
            config: parsedConfig,
            is_active: active,
          }),
        });
      } else {
        await api<Campaign>("/admin/campaigns", {
          method: "POST",
          body: JSON.stringify({
            code: code.trim(),
            name: name.trim(),
            type,
            starts_on: startsOn,
            ends_on: endsOn,
            config: parsedConfig,
          }),
        });
      }
      onDone();
      router.refresh();
    } catch (saveError) {
      setError(
        saveError instanceof ApiError && saveError.status === 409
          ? "รหัสกิจกรรมนี้มีอยู่แล้ว"
          : saveError instanceof ApiError && saveError.status === 422
            ? `ข้อมูลไม่ถูกต้อง: ${saveError.detail}`
            : messageFor(saveError),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {campaign ? null : (
        <Labelled label="รหัสกิจกรรม (ภาษาอังกฤษ ห้ามซ้ำ)" id="code">
          <input
            id="code"
            type="text"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="daily-10km-2027"
            className={inputClass}
          />
        </Labelled>
      )}

      <Labelled label="ชื่อกิจกรรม" id="campaign-name">
        <input
          id="campaign-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="วันละ 10 กิโลเมตร"
          className={inputClass}
        />
      </Labelled>

      {campaign ? null : (
        <Labelled label="ประเภท" id="type">
          <select
            id="type"
            value={type}
            onChange={(event) => {
              setType(event.target.value);
              setConfig({});
            }}
            className={inputClass}
          >
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <p className="mt-2 text-sm text-muted">
            เปลี่ยนประเภทหลังสร้างไม่ได้ — แต้มที่คำนวณไปแล้วจะเปลี่ยนความหมาย
          </p>
        </Labelled>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Labelled label="เริ่ม" id="starts-on">
          <input
            id="starts-on"
            type="date"
            value={startsOn}
            onChange={(event) => setStartsOn(event.target.value)}
            className={inputClass}
          />
        </Labelled>
        <Labelled label="สิ้นสุด" id="ends-on">
          <input
            id="ends-on"
            type="date"
            value={endsOn}
            onChange={(event) => setEndsOn(event.target.value)}
            className={inputClass}
          />
        </Labelled>
      </div>
      {!datesOk && startsOn !== "" && endsOn !== "" ? (
        <p className="text-sm font-medium text-red-700 dark:text-red-400">
          วันสิ้นสุดต้องไม่ก่อนวันเริ่ม
        </p>
      ) : null}

      <div className="rounded-lg border border-border p-3">
        <p className="text-base font-semibold">เงื่อนไขการคิดแต้ม</p>
        <p className="mt-1 mb-3 text-sm text-amber-800 dark:text-amber-300">
          ⚠️ การแก้ค่าเหล่านี้มีผลต่อการคำนวณ — ระบบคิดแต้มจากกฎปัจจุบันเสมอ
          ดังนั้นแต้มของสมาชิกทุกคนจะถูกคำนวณใหม่ตามค่าที่ตั้งไว้ ไม่ใช่ค่าที่ใช้ตอนพวกเขาวิ่ง
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {fields.map((field) => (
            <Labelled key={field.key} label={field.label} id={`cfg-${field.key}`}>
              <input
                id={`cfg-${field.key}`}
                type="text"
                inputMode="numeric"
                value={config[field.key] ?? ""}
                onChange={(event) =>
                  setConfig((current) => ({ ...current, [field.key]: event.target.value }))
                }
                placeholder={field.hint}
                className={inputClass}
              />
            </Labelled>
          ))}
        </div>
      </div>

      {campaign ? (
        <label className="flex items-start gap-2.5 rounded-lg border border-border p-3 text-sm">
          <input
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
            className="mt-0.5"
          />
          <span>
            เปิดใช้งาน
            <span className="mt-1 block text-sm text-muted">
              ปิดไว้ = กิจกรรมจบแล้ว สมาชิกจะไม่เห็นในหน้าแดชบอร์ด
              แต่ผลวิ่งและแต้มที่เกิดขึ้นแล้วยังอยู่ครบ
            </span>
          </span>
        </label>
      ) : null}

      {error ? (
        <p role="alert" className="text-base font-medium text-red-700 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void save()}
        disabled={!canSave}
        className="btn btn-primary w-full sm:w-auto"
      >
        {busy ? "กำลังบันทึก…" : campaign ? "บันทึก" : "สร้างกิจกรรม"}
      </button>
    </div>
  );
}

function Labelled({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-base font-semibold">
        {label}
      </label>
      {children}
    </div>
  );
}

const inputClass = "input-field";
