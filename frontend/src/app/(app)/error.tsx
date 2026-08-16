"use client";

import { useEffect } from "react";

/**
 * The fallback for any screen in this group without its own boundary. Deliberately says
 * nothing about what failed: on the health screen the thrown detail could carry a
 * measurement, and this component cannot know which screen it is standing in for.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // The digest only — never the message, for the same reason.
    console.error("page failed", error.digest ?? "no digest");
  }, [error]);

  return (
    <div className="mx-auto max-w-sm py-10 text-center">
      <p className="text-xl font-bold">โหลดหน้านี้ไม่สำเร็จ</p>
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
