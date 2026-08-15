"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Card, EmptyState } from "@/components/ui";
import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDecimal } from "@/lib/format";
import type { AdminReward, Campaign } from "@/lib/types";

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
        <p className="text-sm text-muted">
          ของรางวัลของกิจกรรม <span className="font-medium">{campaign.name}</span>
        </p>
        <button
          type="button"
          onClick={() => setCreating((open) => !open)}
          className="rounded-lg border border-border px-3 py-2 text-sm"
        >
          {creating ? "ยกเลิก" : "+ เพิ่มของรางวัล"}
        </button>
      </div>

      {creating ? (
        <Card>
          <p className="mb-3 font-medium">เพิ่มของรางวัลใหม่</p>
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
          <p className="font-medium">แก้ไข {reward.name}</p>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-sm text-muted underline"
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
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{reward.name}</span>
            {reward.is_active ? null : <Badge>เลิกแจกแล้ว</Badge>}
            {reward.is_active && reward.stock === 0 ? <Badge>ของหมด</Badge> : null}
          </div>
          <p className="mt-0.5 text-sm text-muted tabular-nums">
            {formatDecimal(reward.points_cost)} แต้ม · เหลือ {reward.stock} ชิ้น
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="shrink-0 rounded-lg border border-border px-3 py-2 text-sm"
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
  const [cost, setCost] = useState(reward?.points_cost ?? "");
  const [stock, setStock] = useState(reward ? String(reward.stock) : "");
  const [active, setActive] = useState(reward?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const costOk = COST_RE.test(cost.trim()) && /[1-9]/.test(cost);
  const stockOk = /^\d{1,5}$/.test(stock.trim());
  const canSave = name.trim() !== "" && costOk && stockOk && !busy;

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
        <label htmlFor={`name-${reward?.id ?? "new"}`} className="mb-1 block text-sm font-medium">
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

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={`cost-${reward?.id ?? "new"}`} className="mb-1 block text-sm font-medium">
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
          <label htmlFor={`stock-${reward?.id ?? "new"}`} className="mb-1 block text-sm font-medium">
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
            <span className="mt-0.5 block text-xs text-muted">
              ปิดไว้ = เลิกแจก สมาชิกจะไม่เห็นในหน้ารางวัล
              แต่รายการที่เคยแลกไปแล้วยังอยู่ครบ (ไม่มีการลบของรางวัล)
            </span>
          </span>
        </label>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void save()}
        disabled={!canSave}
        className="w-full rounded-lg bg-brand px-4 py-3 font-medium text-white active:opacity-80 disabled:opacity-40 sm:w-auto sm:px-6"
      >
        {busy ? "กำลังบันทึก…" : reward ? "บันทึก" : "เพิ่มของรางวัล"}
      </button>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base outline-none focus:border-brand";
