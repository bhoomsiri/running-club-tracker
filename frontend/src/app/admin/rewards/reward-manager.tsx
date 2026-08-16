"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Badge, Card, EmptyState } from "@/components/ui";
import { ZoomableImage } from "@/components/zoomable-image";
import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDecimal } from "@/lib/format";
import type { AdminReward, Campaign, RewardImageUpload } from "@/lib/types";

/**
 * The reward catalogue.
 *
 * There is no delete, by design: a reward someone has already redeemed is part of the
 * ledger's history, and removing it would leave redemptions pointing at nothing. Setting
 * it inactive withdraws it from the members' list while the record stays intact — so
 * retired rewards are shown here, greyed rather than hidden, or they would look deleted
 * and be recreated.
 *
 * Points cost is a string from the input box to the request body. It is what members
 * spend, and the backend keeps it as a Decimal so it survives exactly as typed.
 *
 * The photo is uploaded first and attached second: the upload returns a key, and the
 * create/update call that stores it on the reward is the one that writes the audit row.
 * A picture uploaded but never attached is an orphan in the bucket, which is the cheap
 * failure — the expensive one would be a reward pointing at something that was never
 * checked.
 */

const COST_RE = /^\d{1,4}(\.\d{1,2})?$/;

export function RewardManager({
  campaign,
  rewards,
}: {
  campaign: Campaign;
  rewards: AdminReward[];
}) {
  const [creating, setCreating] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-base text-muted">
          ของรางวัลของกิจกรรม <span className="text-lg font-semibold">{campaign.name}</span>
        </p>
        <button
          type="button"
          onClick={() => setCreating((open) => !open)}
          className="btn btn-secondary"
        >
          {creating ? "ยกเลิก" : "+ เพิ่มของรางวัล"}
        </button>
      </div>

      {creating ? (
        <Card>
          <p className="mb-3 text-lg font-semibold">เพิ่มของรางวัลใหม่</p>
          <RewardForm campaignId={campaign.id} onDone={() => setCreating(false)} />
        </Card>
      ) : null}

      {rewards.length === 0 ? (
        <EmptyState>
          ยังไม่มีของรางวัลในกิจกรรมนี้ — สมาชิกจะเห็นหน้ารางวัลว่าง จนกว่าจะเพิ่มรายการแรก
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {rewards.map((reward) => (
            <li key={reward.id}>
              <RewardRow reward={reward} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RewardRow({ reward }: { reward: AdminReward }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <p className="text-lg font-semibold">แก้ไข {reward.name}</p>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-base text-muted underline"
          >
            ยกเลิก
          </button>
        </div>
        <RewardForm reward={reward} onDone={() => setEditing(false)} />
      </Card>
    );
  }

  return (
    <Card className={reward.is_active ? "" : "opacity-60"}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {reward.image_url !== null ? (
          <ZoomableImage
            src={reward.image_url}
            alt={reward.name}
            className="h-16 w-16 rounded-lg object-cover"
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold">{reward.name}</span>
            {reward.is_active ? null : <Badge>เลิกแจกแล้ว</Badge>}
            {reward.is_active && reward.stock === 0 ? <Badge>ของหมด</Badge> : null}
          </div>
          <p className="mt-0.5 text-sm text-muted tabular-nums">
            {formatDecimal(reward.points_cost)} แต้ม · เหลือ {reward.stock} ชิ้น
            {reward.image_url === null ? " · ยังไม่มีรูป" : ""}
          </p>
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

function RewardForm({
  campaignId,
  reward,
  onDone,
}: {
  campaignId?: string;
  reward?: AdminReward;
  onDone: () => void;
}) {
  const api = useApi();
  const router = useRouter();

  const [name, setName] = useState(reward?.name ?? "");
  // 1 by default: this club's rewards are one-point items, and a cost typed fresh every
  // time is a cost that eventually gets typed wrong.
  const [cost, setCost] = useState(reward?.points_cost ?? "1");
  const [stock, setStock] = useState(reward ? String(reward.stock) : "");
  const [active, setActive] = useState(reward?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // null means "no new photo" — on edit that leaves the existing one alone, because the
  // backend reads an absent image_key as unchanged.
  const [imageKey, setImageKey] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(reward?.image_url ?? null);
  const [uploading, setUploading] = useState(false);
  const objectUrl = useRef<string | null>(null);

  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );

  const costOk = COST_RE.test(cost.trim()) && /[1-9]/.test(cost);
  const stockOk = /^\d{1,5}$/.test(stock.trim());
  const canSave = name.trim() !== "" && costOk && stockOk && !busy && !uploading;

  async function onFileChosen(file: File) {
    setError(null);
    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const uploaded = await api<RewardImageUpload>("/admin/rewards/image", {
        method: "POST",
        body,
      });
      setImageKey(uploaded.image_key);

      // Shown from the local file rather than by fetching the object back: the picture
      // is already on this machine, and the presigned URL arrives with the next reload.
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = URL.createObjectURL(file);
      setPreview(objectUrl.current);
    } catch (uploadError) {
      setError(
        uploadError instanceof ApiError && uploadError.status === 415
          ? "ไฟล์นี้ไม่ใช่รูปภาพที่รองรับ — ใช้ JPG, PNG หรือ WEBP"
          : messageFor(uploadError),
      );
    } finally {
      setUploading(false);
    }
  }

  async function save() {
    if (!canSave) return;
    setError(null);
    setBusy(true);
    try {
      if (reward) {
        await api<AdminReward>(`/admin/rewards/${reward.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: name.trim(),
            points_cost: cost.trim(),
            stock: Number(stock),
            is_active: active,
            // Omitted when no new photo was chosen: JSON.stringify drops undefined, and
            // the backend reads a missing key as "leave it as it is".
            image_key: imageKey ?? undefined,
          }),
        });
      } else {
        await api<AdminReward>("/admin/rewards", {
          method: "POST",
          body: JSON.stringify({
            campaign_id: campaignId,
            name: name.trim(),
            points_cost: cost.trim(),
            stock: Number(stock),
            image_key: imageKey ?? undefined,
          }),
        });
      }
      onDone();
      router.refresh();
    } catch (saveError) {
      setError(
        saveError instanceof ApiError && saveError.status === 422
          ? "ค่าที่กรอกไม่ถูกต้อง — แต้มต้องมากกว่า 0 และจำนวนต้องไม่ติดลบ"
          : messageFor(saveError),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor={`name-${reward?.id ?? "new"}`} className="mb-2 block text-base font-semibold">
          ชื่อของรางวัล
        </label>
        <input
          id={`name-${reward?.id ?? "new"}`}
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="เช่น เสื้อวิ่งประจำปี"
          className={inputClass}
        />
      </div>

      <div>
        <label
          htmlFor={`image-${reward?.id ?? "new"}`}
          className="mb-2 block text-base font-semibold"
        >
          รูปของรางวัล <span className="font-normal text-muted">(ไม่บังคับ)</span>
        </label>
        <div className="flex items-center gap-3">
          {preview !== null ? (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={preview}
              alt="ตัวอย่างรูปของรางวัล"
              className="h-20 w-20 shrink-0 rounded-lg bg-border object-cover"
            />
          ) : (
            <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-lg border border-dashed border-border text-2xl text-muted">
              🎁
            </div>
          )}
          <div className="min-w-0">
            <input
              id={`image-${reward?.id ?? "new"}`}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={uploading}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void onFileChosen(file);
              }}
              className="block w-full text-sm file:mr-3 file:rounded-lg file:border file:border-border file:bg-background file:px-3 file:py-2 file:text-sm"
            />
            <p className="mt-2 text-sm text-muted">
              {uploading
                ? "กำลังอัปโหลด…"
                : imageKey !== null
                  ? "อัปโหลดแล้ว — กดบันทึกเพื่อผูกกับของรางวัลนี้"
                  : "JPG, PNG หรือ WEBP ไม่เกิน 10 MB"}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={`cost-${reward?.id ?? "new"}`} className="mb-2 block text-base font-semibold">
            ใช้กี่แต้ม
          </label>
          <input
            id={`cost-${reward?.id ?? "new"}`}
            type="text"
            inputMode="decimal"
            value={cost}
            onChange={(event) => setCost(event.target.value)}
            placeholder="10"
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor={`stock-${reward?.id ?? "new"}`} className="mb-2 block text-base font-semibold">
            จำนวนที่มี
          </label>
          <input
            id={`stock-${reward?.id ?? "new"}`}
            type="text"
            inputMode="numeric"
            value={stock}
            onChange={(event) => setStock(event.target.value)}
            placeholder="20"
            className={inputClass}
          />
        </div>
      </div>

      {reward ? (
        <label className="flex items-start gap-2.5 rounded-lg border border-border p-3 text-sm">
          <input
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
            className="mt-0.5"
          />
          <span>
            เปิดให้แลก
            <span className="mt-1 block text-sm text-muted">
              ปิดไว้ = เลิกแจก สมาชิกจะไม่เห็นในหน้ารางวัล
              แต่รายการที่เคยแลกไปแล้วยังอยู่ครบ (ไม่มีการลบของรางวัล)
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
        {busy ? "กำลังบันทึก…" : reward ? "บันทึก" : "เพิ่มของรางวัล"}
      </button>
    </div>
  );
}

const inputClass = "input-field";
