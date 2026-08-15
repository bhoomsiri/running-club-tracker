"use client";

import { useEffect } from "react";

/**
 * Server-rendered failures land here. Next redacts the real message in production and
 * hands over a digest instead, so there is nothing specific to show the member — what
 * matters is that the screen is not blank and that trying again is one tap away.
 */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // The digest is what ties this screen to the server log entry.
    console.error("dashboard failed", error.digest ?? error.message);
  }, [error]);

  return (
    <div className="mx-auto max-w-sm py-10 text-center">
      <p className="text-lg font-medium">โหลดข้อมูลไม่สำเร็จ</p>
      <p className="mt-2 text-sm text-muted">
        อาจเป็นปัญหาการเชื่อมต่อชั่วคราว ลองใหม่อีกครั้งได้เลย
      </p>
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
