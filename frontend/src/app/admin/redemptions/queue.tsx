"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Card, EmptyState } from "@/components/ui";
import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDate, formatDecimal } from "@/lib/format";
import type { FulfilBlock, PendingRedemption, Redemption } from "@/lib/types";

/**
 * The queue of rewards waiting to be handed over.
 *
 * Whether an item can go out is decided by the backend and shown here, so the reason
 * appears next to it rather than as a rejection after the button is pressed. The button
 * is disabled when blocked, and the sentence beside it says what to do about it — both
 * blocks are things the superuser can resolve, one by reviewing a run and one by
 * correcting the points.
 *
 * Cancelling refunds the points and returns the stock, inside one transaction. Nothing
 * here is a deletion.
 */

const BLOCK_REASONS: Record<FulfilBlock, string> = {
  unresolved_runs:
    "สมาชิกมีผลวิ่งรอตรวจอยู่ — ตัดสินผลวิ่งนั้นก่อน แล้วจึงส่งของได้ (ถ้าผลวิ่งไม่ผ่าน แต้มจะถูกหักคืนและอาจไม่พอ)",
  negative_balance:
    "แต้มคงเหลือติดลบ เพราะมีผลวิ่งถูกตัดสินว่าไม่ผ่านหลังจากแลกไปแล้ว — ยกเลิกรายการนี้เพื่อคืนแต้ม หรือรอให้สมาชิกสะสมเพิ่ม",
};

export function RedemptionQueue({ rows }: { rows: PendingRedemption[] }) {
  if (rows.length === 0) {
    return <EmptyState>ไม่มีของรางวัลที่รอส่ง</EmptyState>;
  }

  return (
    <ul className="space-y-3">
      {rows.map((row) => (
        <li key={row.redemption.id}>
          <QueueRow row={row} />
        </li>
      ))}
    </ul>
  );
}

function QueueRow({ row }: { row: PendingRedemption }) {
  const api = useApi();
  const router = useRouter();
  const [busy, setBusy] = useState<"fulfill" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(action: "fulfill" | "cancel") {
    setError(null);
    setBusy(action);
    try {
      await api<Redemption>(`/admin/redemptions/${row.redemption.id}/${action}`, {
        method: "POST",
      });
      router.refresh();
    } catch (actError) {
      setError(
        actError instanceof ApiError && actError.status === 409
          ? // The queue's copy was stale — the server just decided otherwise.
            `ยังส่งของไม่ได้: ${actError.detail}`
          : messageFor(actError),
      );
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  const blocked = row.blocked_by !== null;

  return (
    <Card>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{row.reward_name}</span>
            {blocked ? <Badge>ยังส่งไม่ได้</Badge> : <Badge tone="success">พร้อมส่ง</Badge>}
          </div>
          <p className="mt-0.5 text-sm text-muted tabular-nums">
            {row.member_name} · ใช้ {formatDecimal(row.redemption.points_spent)} แต้ม ·
            แลกเมื่อ {formatDate(row.redemption.created_at)}
          </p>
          <p className="mt-0.5 text-xs text-muted tabular-nums">
            แต้มคงเหลือตอนนี้ {formatDecimal(row.balance)}
          </p>
        </div>

        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => void act("fulfill")}
            disabled={blocked || busy !== null}
            className="rounded-lg bg-brand px-3 py-2 text-sm font-medium text-white active:opacity-80 disabled:opacity-40"
          >
            {busy === "fulfill" ? "กำลังบันทึก…" : "ส่งของแล้ว"}
          </button>
          <button
            type="button"
            onClick={() => void act("cancel")}
            disabled={busy !== null}
            className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-40"
          >
            {busy === "cancel" ? "กำลังยกเลิก…" : "ยกเลิก คืนแต้ม"}
          </button>
        </div>
      </div>

      {row.blocked_by !== null ? (
        <p className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200">
          {BLOCK_REASONS[row.blocked_by]}
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
