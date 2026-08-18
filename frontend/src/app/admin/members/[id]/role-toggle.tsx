"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card } from "@/components/ui";
import { messageFor } from "@/lib/api";
import { useApi } from "@/lib/api-client";
import { ROLE_LABELS } from "@/lib/roles";
import type { Member, Role } from "@/lib/types";

/**
 * Making somebody a helper, or taking it back. Rendered for the superuser alone.
 *
 * Deliberately plain about what it grants, because the person pressing it is deciding
 * who may read other members' health and contact details — not adjusting a preference.
 * The backend refuses this call from anyone but the superuser whatever this screen
 * renders, and refuses it for the superuser's own row at all.
 */
export function RoleToggle({ member }: { member: Member }) {
  const api = useApi();
  const router = useRouter();
  const [role, setRole] = useState<Role>(member.role);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (role === "superuser") {
    return (
      <Card>
        <p className="text-base">
          {member.name} เป็นผู้ดูแลระบบ — สิทธิ์นี้เปลี่ยนจากหน้านี้ไม่ได้
        </p>
      </Card>
    );
  }

  const isAdmin = role === "admin";
  const next: Role = isAdmin ? "member" : "admin";

  async function change() {
    setError(null);
    setBusy(true);
    try {
      const updated = await api<Member>(`/admin/members/${member.id}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: next }),
      });
      setRole(updated.role);
      // The badge in the page header and the club overview both read this role.
      router.refresh();
    } catch (changeError) {
      setError(messageFor(changeError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <p className="text-lg font-semibold">สิทธิ์ผู้ดูแล</p>
      <p className="mt-1 text-base text-muted">
        ตอนนี้: {ROLE_LABELS[role]} ·{" "}
        {isAdmin
          ? "เปิดดูข้อมูลสุขภาพ/คัดกรอง/ติดต่อ ของสมาชิกได้ และตัดสินผลวิ่งได้"
          : "ผู้ดูแลจะเปิดดูข้อมูลอ่อนไหวของสมาชิกได้ (ระบบบันทึกทุกครั้ง) และตัดสินผลวิ่งได้"}
      </p>

      <button
        type="button"
        onClick={() => void change()}
        disabled={busy}
        className={`btn mt-4 w-full ${isAdmin ? "btn-secondary" : "btn-primary"}`}
      >
        {busy ? "กำลังบันทึก…" : isAdmin ? "ถอดสิทธิ์ผู้ดูแล" : "ตั้งเป็นผู้ดูแล"}
      </button>

      {error ? (
        <p role="alert" className="mt-3 text-base font-medium text-red-700 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
