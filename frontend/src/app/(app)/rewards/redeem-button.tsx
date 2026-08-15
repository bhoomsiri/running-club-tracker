"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import type { Redemption } from "@/lib/types";

/**
 * The one interactive part of the catalogue, so the rest of the page can stay on the
 * server.
 *
 * A 409 here is not really an error: it means the world moved between the page being
 * rendered and the button being pressed — the last one in stock went, or points were
 * spent in another tab. The backend settles that inside one transaction, and the honest
 * response is to say so and show the member the current numbers.
 */
export function RedeemButton({
  rewardId,
  rewardName,
  disabledReason,
}: {
  rewardId: string;
  rewardName: string;
  disabledReason: string | null;
}) {
  const api = useApi();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (disabledReason !== null) {
    return (
      <div className="text-right">
        <button
          type="button"
          disabled
          className="rounded-lg bg-border px-4 py-2 text-sm font-medium text-muted"
        >
          แลก
        </button>
        <p className="mt-1 text-xs text-muted">{disabledReason}</p>
      </div>
    );
  }

  async function onRedeem() {
    setError(null);
    setBusy(true);
    try {
      await api<Redemption>(`/rewards/${rewardId}/redeem`, { method: "POST" });
      // Re-renders the server component, so the balance and stock on screen are the
      // ones the transaction just left behind.
      router.refresh();
    } catch (redeemError) {
      setError(redeemMessage(redeemError));
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="text-right">
      <button
        type="button"
        onClick={() => void onRedeem()}
        disabled={busy}
        aria-label={`แลก ${rewardName}`}
        className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white active:opacity-80 disabled:opacity-50"
      >
        {busy ? "กำลังแลก…" : "แลก"}
      </button>
      {error ? (
        <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function redeemMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return messageFor(error);
  switch (error.status) {
    case 409:
      return "แลกไม่สำเร็จ — แต้มไม่พอหรือของเพิ่งหมดพอดี ตัวเลขด้านบนอัปเดตแล้ว";
    case 404:
      return "ไม่พบของรางวัลชิ้นนี้แล้ว";
    case 422:
      return "คำขอไม่ถูกต้อง กรุณาลองใหม่";
    default:
      return messageFor(error);
  }
}
