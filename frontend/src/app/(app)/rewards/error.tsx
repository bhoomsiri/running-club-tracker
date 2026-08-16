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
      <p className="text-xl font-bold">โหลดรายการรางวัลไม่สำเร็จ</p>
      <p className="mt-2 text-base text-muted">ลองใหม่อีกครั้งได้เลย</p>
      <button
        type="button"
        onClick={reset}
        className="btn btn-primary mt-6 w-full"
      >
        ลองใหม่
      </button>
      {error.digest ? (
        <p className="mt-4 font-mono text-sm text-muted">รหัสอ้างอิง {error.digest}</p>
      ) : null}
    </div>
  );
}
