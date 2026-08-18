import Link from "next/link";
import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import { getMySummary } from "@/lib/me";
import type { Campaign } from "@/lib/types";

import { CampaignManager } from "./campaign-manager";

export default async function AdminCampaignsPage() {
  const summary = await getMySummary();
  if (summary.member.role !== "superuser") {
    redirect("/dashboard");
  }

  const campaigns = await apiServer<Campaign[]>("/admin/campaigns");

  return (
    <>
      <Link href="/admin" className="text-base text-muted underline">
        ‹ กลับไปภาพรวม
      </Link>

      <header className="mt-4 mb-6">
        <h1 className="text-2xl font-bold tracking-tight">จัดการกิจกรรม</h1>
        <p className="mt-2 text-base text-muted">
          กิจกรรมที่ปิดแล้วยังแสดงอยู่ เพราะการแก้ไขย้อนหลังต้องทำได้
        </p>
      </header>

      <CampaignManager campaigns={campaigns} />
    </>
  );
}
