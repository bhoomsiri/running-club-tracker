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
      <p className="text-xl font-bold">โหลดข้อมูลไม่สำเร็จ</p>
      <p className="mt-2 text-base text-muted">
        อาจเป็นปัญหาการเชื่อมต่อชั่วคราว ลองใหม่อีกครั้งได้เลย
      </p>
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
