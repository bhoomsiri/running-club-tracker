"use client";

import { useEffect } from "react";

export default function RewardsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("rewards failed", error.digest ?? error.message);
  }, [error]);

  return (
    <div className="mx-auto max-w-sm py-10 text-center">
      <p className="text-lg font-medium">โหลดรายการรางวัลไม่สำเร็จ</p>
      <p className="mt-2 text-sm text-muted">ลองใหม่อีกครั้งได้เลย</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 w-full rounded-lg bg-brand px-4 py-3 font-medium text-white active:opacity-80"
      >
        ลองใหม่
      </button>
      {error.digest ? (
        <p className="mt-4 font-mono text-xs text-muted">รหัสอ้างอิง {error.digest}</p>
      ) : null}
    </div>
  );
}
