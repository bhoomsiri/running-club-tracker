"use client";

import { useState } from "react";

import { messageFor } from "@/lib/api";
import { useApiDownload } from "@/lib/api-client";

/**
 * Download the club's records as one Excel workbook.
 *
 * Rendered only for the superuser, and that is a courtesy: the backend refuses
 * /admin/export to anyone else whatever this component does, and the export is written
 * to the audit log either way. Hiding the button spares an admin a 403, it does not
 * decide anything.
 *
 * The file arrives as a blob rather than a link the browser follows, because the request
 * has to carry a Clerk token — a plain <a href> would send no Authorization header and
 * get a 401. The object URL is revoked immediately after the click; leaving it alive
 * would keep a spreadsheet full of the club's records in memory for the tab's lifetime.
 */
export function ExportButton() {
  const download = useApiDownload();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    setBusy(true);
    try {
      const { blob, filename } = await download("/admin/export");
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch (downloadError) {
      setError(messageFor(downloadError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        className="min-h-12 rounded-control border border-border px-4 text-base disabled:opacity-40"
      >
        {busy ? "กำลังสร้างไฟล์…" : "ดาวน์โหลด Excel"}
      </button>

      {/* Deliberately does not read the health flag: that would mean an endpoint whose
          only job is to tell the frontend a server setting, and the sentence is true
          either way. The file itself says which sheets it has. */}
      <p className="mt-2 text-sm text-muted">
        สมาชิก · ผลวิ่ง · การแลกรางวัล · แต้ม · ของรางวัล · กิจกรรม
        <br />
        ชีตข้อมูลสุขภาพ แบบคัดกรอง และข้อมูลติดต่อ จะรวมมาก็ต่อเมื่อเปิดใช้งานไว้ —
        และทุกครั้งที่ดาวน์โหลดจะถูกบันทึกการเข้าถึงไว้เป็นรายบุคคล
      </p>

      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}
