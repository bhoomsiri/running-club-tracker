import Link from "next/link";
import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import { getMySummary } from "@/lib/me";
import type { PendingRedemption } from "@/lib/types";

import { RedemptionQueue } from "./queue";

export default async function AdminRedemptionsPage() {
  const summary = await getMySummary();
  if (summary.member.role !== "superuser") {
    redirect("/dashboard");
  }

  const rows = await apiServer<PendingRedemption[]>("/admin/redemptions");
  const blocked = rows.filter((row) => row.blocked_by !== null).length;

  return (
    <>
      <Link href="/admin" className="text-base text-muted underline">
        ‹ กลับไปภาพรวม
      </Link>

      <header className="mt-4 mb-6">
        <h1 className="text-2xl font-bold tracking-tight">คิวของรางวัล</h1>
        <p className="mt-2 text-base text-muted">
          รอส่ง {rows.length} รายการ
          {blocked > 0 ? ` · ยังส่งไม่ได้ ${blocked} รายการ` : ""}
        </p>
      </header>

      <RedemptionQueue rows={rows} />
    </>
  );
}
