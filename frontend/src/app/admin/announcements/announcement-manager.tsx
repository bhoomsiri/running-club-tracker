"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AnnouncementBody } from "@/components/announcement-body";
import { Badge, Card, EmptyState } from "@/components/ui";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { formatDate } from "@/lib/format";
import type { AdminAnnouncement } from "@/lib/types";

/**
 * The notice board.
 *
 * Two things are said out loud in the UI rather than left to be understood. A new notice
 * is saved as a draft unless the author ticks the box, so writing and publishing are two
 * decisions. And the text goes on a page anyone can open without signing in — which is
 * the point of it, but also the reason a member's name or anything about their health
 * must never be typed into it.
 */
export function AnnouncementManager({
  announcements,
}: {
  announcements: AdminAnnouncement[];
}) {
  const [writing, setWriting] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-base text-muted">ทั้งหมด {announcements.length} รายการ</p>
        <button
          type="button"
          onClick={() => setWriting((open) => !open)}
          className="btn btn-secondary"
        >
          {writing ? "ยกเลิก" : "+ เขียนประกาศใหม่"}
        </button>
      </div>

      {writing ? (
        <Card>
          <p className="mb-3 text-lg font-semibold">ประกาศใหม่</p>
          <AnnouncementForm onDone={() => setWriting(false)} />
        </Card>
      ) : null}

      {announcements.length === 0 ? (
        <EmptyState>
          ยังไม่มีประกาศ — เขียนอันแรกได้เลย จะขึ้นทั้งหน้าแรกของเว็บและหน้าแดชบอร์ดของสมาชิก
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {announcements.map((announcement) => (
            <li key={announcement.id}>
              <AnnouncementRow announcement={announcement} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AnnouncementRow({ announcement }: { announcement: AdminAnnouncement }) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <Card>
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="min-w-0 truncate text-lg font-semibold">แก้ไข {announcement.title}</p>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="tap shrink-0 text-base text-muted underline"
          >
            ยกเลิก
          </button>
        </div>
        <AnnouncementForm
          announcement={announcement}
          onDone={() => setEditing(false)}
        />
      </Card>
    );
  }

  return (
    <Card className={announcement.is_published ? "" : "opacity-70"}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold">{announcement.title}</span>
            {announcement.is_published ? (
              <Badge tone="success">เผยแพร่อยู่</Badge>
            ) : (
              <Badge>ร่าง / ซ่อนอยู่</Badge>
            )}
          </div>
          <p className="mt-2 text-base text-muted tabular-nums">
            {formatDate(announcement.created_at)}
          </p>
          <AnnouncementBody
            body={announcement.body}
            className="mt-2 line-clamp-3 text-sm"
          />
        </div>

        <div className="flex shrink-0 gap-2">
          <PublishToggle announcement={announcement} />
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="btn btn-secondary"
          >
            แก้ไข
          </button>
        </div>
      </div>
    </Card>
  );
}

function PublishToggle({ announcement }: { announcement: AdminAnnouncement }) {
  const api = useApi();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setError(null);
    setBusy(true);
    try {
      await api<AdminAnnouncement>(`/admin/announcements/${announcement.id}`, {
        method: "PATCH",
        // Only this field: the text is left exactly as it was.
        body: JSON.stringify({ is_published: !announcement.is_published }),
      });
      router.refresh();
    } catch (toggleError) {
      setError(messageFor(toggleError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => void toggle()}
        disabled={busy}
        className="btn btn-secondary"
      >
        {busy ? "…" : announcement.is_published ? "ซ่อน" : "เผยแพร่"}
      </button>
      {error ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-700 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function AnnouncementForm({
  announcement,
  onDone,
}: {
  announcement?: AdminAnnouncement;
  onDone: () => void;
}) {
  const api = useApi();
  const router = useRouter();

  const [title, setTitle] = useState(announcement?.title ?? "");
  const [body, setBody] = useState(announcement?.body ?? "");
  const [published, setPublished] = useState(announcement?.is_published ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSave = title.trim() !== "" && body.trim() !== "" && !busy;
  const id = announcement?.id ?? "new";

  async function save() {
    if (!canSave) return;
    setError(null);
    setBusy(true);
    try {
      const payload = {
        title: title.trim(),
        body: body.trim(),
        is_published: published,
      };
      if (announcement) {
        await api<AdminAnnouncement>(`/admin/announcements/${announcement.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      } else {
        await api<AdminAnnouncement>("/admin/announcements", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      onDone();
      router.refresh();
    } catch (saveError) {
      setError(messageFor(saveError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="rounded-control border border-amber-500/50 bg-amber-500/15 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
        ข้อความนี้แสดงบนหน้าแรกของเว็บ ซึ่งเปิดให้ทุกคนอ่านได้โดยไม่ต้องเข้าสู่ระบบ —
        อย่าใส่ชื่อ เบอร์โทร หรือข้อมูลสุขภาพของสมาชิก
      </p>

      <div>
        <label htmlFor={`title-${id}`} className="mb-2 block text-base font-semibold">
          หัวข้อ
        </label>
        <input
          id={`title-${id}`}
          type="text"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="เช่น ซ้อมวิ่งเช้าวันเสาร์"
          maxLength={200}
          className={inputClass}
        />
      </div>

      <div>
        <label htmlFor={`body-${id}`} className="mb-2 block text-base font-semibold">
          เนื้อหา
        </label>
        <textarea
          id={`body-${id}`}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          rows={6}
          placeholder={"เจอกันหน้าตึกอำนวยการ 05:30 น.\nใครมาใหม่ทักได้เลย"}
          maxLength={20000}
          className={`${inputClass} resize-y`}
        />
        <p className="mt-2 text-sm text-muted">ขึ้นบรรทัดใหม่ได้ ระบบจะแสดงตามที่พิมพ์</p>
      </div>

      <label className="flex items-start gap-2.5 rounded-lg border border-border p-3 text-sm">
        <input
          type="checkbox"
          checked={published}
          onChange={(event) => setPublished(event.target.checked)}
          className="mt-0.5"
        />
        <span>
          เผยแพร่
          <span className="mt-1 block text-sm text-muted">
            ไม่ติ๊ก = เก็บเป็นร่าง เห็นเฉพาะหน้านี้ ยังไม่มีใครเห็น
          </span>
        </span>
      </label>

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
        {busy ? "กำลังบันทึก…" : announcement ? "บันทึก" : "สร้างประกาศ"}
      </button>
    </div>
  );
}

const inputClass = "input-field";
