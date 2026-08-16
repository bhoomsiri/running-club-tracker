import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import type { AdminAnnouncement, MemberSummary } from "@/lib/types";

import { AnnouncementManager } from "./announcement-manager";

/**
 * Writing the club's news. Superuser only, checked here and again by the backend.
 *
 * Drafts are listed alongside published notices: hiding is how a notice is taken down,
 * so one that vanished from this screen would look deleted and be written again.
 */
export default async function AdminAnnouncementsPage() {
  const summary = await apiServer<MemberSummary>("/me/summary");
  if (summary.member.role !== "superuser") {
    redirect("/dashboard");
  }

  const announcements = await apiServer<AdminAnnouncement[]>("/admin/announcements");

  return (
    <>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">ข่าวประชาสัมพันธ์</h1>
        <p className="mt-1 text-sm text-muted">
          เขียนประกาศของชมรม เผยแพร่หรือซ่อนได้ตลอด
        </p>
      </header>

      <AnnouncementManager announcements={announcements} />
    </>
  );
}
