import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import type { ClubOverview, MemberSummary } from "@/lib/types";

import { OverviewTable } from "./overview-table";

/**
 * The club-wide view, for the superuser.
 *
 * Outside the (app) route group on purpose, for the same reason /onboarding is: the
 * superuser is exempt from the onboarding gate, so running them through it would be
 * pointless, and this screen is not part of the member navigation.
 *
 * The guard here is a courtesy — a nicer answer than a raw 403 for someone who followed
 * a link they should not have. The control is the backend, which refuses /admin/overview
 * to anyone who is not the superuser whatever this page does.
 */
export default async function AdminPage() {
  const summary = await apiServer<MemberSummary>("/me/summary");
  if (summary.member.role !== "superuser") {
    redirect("/dashboard");
  }

  const overview = await apiServer<ClubOverview>("/admin/overview");

  return (
    <>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">ภาพรวมสมาชิก</h1>
        <p className="mt-1 text-sm text-muted">
          สมาชิก {overview.members.length} คน · กิจกรรมที่เปิดอยู่ {overview.campaigns.length} รายการ
        </p>
      </header>

      <OverviewTable overview={overview} />

      <p className="mt-6 text-xs text-muted">
        หน้านี้ไม่แสดงข้อมูลสุขภาพ แบบคัดกรอง หรือข้อมูลติดต่อ —
        ข้อมูลเหล่านั้นเปิดดูได้ทีละคนผ่านหน้าที่บันทึกการเข้าถึงไว้
      </p>
    </>
  );
}
