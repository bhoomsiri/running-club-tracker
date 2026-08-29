import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import { getMySummary } from "@/lib/me";
import { isStaff, isSuperuser } from "@/lib/roles";
import type { ClubOverview } from "@/lib/types";

import { ExportButton } from "./export-button";
import { OverviewTable } from "./overview-table";

/**
 * The club-wide view, for the staff — admins and the superuser.
 *
 * Outside the (app) route group on purpose, for the same reason /onboarding is: the
 * superuser is exempt from the onboarding gate, so running them through it would be
 * pointless, and this screen is not part of the member navigation.
 *
 * The guard here is a courtesy — a nicer answer than a raw 403 for someone who followed
 * a link they should not have. The control is the backend, which refuses /admin/overview
 * to anyone who is not staff whatever this page does.
 */
export default async function AdminPage() {
  const summary = await getMySummary();
  if (!isStaff(summary.member.role)) {
    redirect("/dashboard");
  }

  const overview = await apiServer<ClubOverview>("/admin/overview");

  return (
    <>
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">ภาพรวมสมาชิก</h1>
        <p className="mt-2 text-base text-muted">
          สมาชิก {overview.members.length} คน · กิจกรรมที่เปิดอยู่ {overview.campaigns.length} รายการ
        </p>
      </header>

      <OverviewTable overview={overview} />

      <p className="mt-6 text-sm text-muted">
        หน้านี้ไม่แสดงข้อมูลสุขภาพ แบบคัดกรอง หรือข้อมูลติดต่อ —
        ข้อมูลเหล่านั้นเปิดดูได้ทีละคนผ่านหน้าที่บันทึกการเข้าถึงไว้
      </p>

      {/* Superuser only, and only as a courtesy: the backend refuses /admin/export to
          an admin whatever this page renders. */}
      {isSuperuser(summary.member.role) ? (
        <section className="mt-8 border-t border-border pt-6">
          <h2 className="mb-3 text-lg font-semibold">ส่งออกข้อมูล</h2>
          <ExportButton />
        </section>
      ) : null}
    </>
  );
}
