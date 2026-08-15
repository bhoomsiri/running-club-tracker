import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Badge, Card } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { formatDecimal } from "@/lib/format";
import type { MemberProfile, MemberSummary, Role } from "@/lib/types";

import { EditProfile } from "./edit-profile";

const ROLE_LABELS: Record<Role, string> = {
  member: "สมาชิก",
  admin: "ผู้ดูแล",
  superuser: "ผู้ดูแลระบบ",
};

export default async function ProfilePage() {
  const [summary, profile] = await Promise.all([
    apiServer<MemberSummary>("/me/summary"),
    apiServer<MemberProfile>("/me/profile"),
  ]);

  return (
    <>
      <PageHeader title="โปรไฟล์" />

      <div className="space-y-4">
        <Card>
          {/* The Thai name is what the club calls them; display_name from Clerk is the
              fallback until they have given one. */}
          <p className="text-lg font-medium">
            {profile.full_name_th ?? summary.member.display_name}
          </p>
          <p className="mt-1">
            <Badge tone={summary.member.role === "member" ? "neutral" : "brand"}>
              {ROLE_LABELS[summary.member.role]}
            </Badge>
          </p>
          <p className="mt-3 text-sm text-muted tabular-nums">
            ระยะสะสมรวม {formatDecimal(summary.total_distance_km)} กม.
          </p>
        </Card>

        <EditProfile profile={profile} />

        {/* Health and the screening live on their own screen: both are behind a consent
            gate, and mixing them into a general profile page makes them look like more
            fields to fill in. */}
        <Link href="/health" className="block">
          <Card className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">ข้อมูลสุขภาพและแบบคัดกรอง</p>
              <p className="mt-0.5 text-sm text-muted">
                บันทึกค่าก่อน/หลังกิจกรรม แก้ไขแบบคัดกรอง และจัดการความยินยอม
              </p>
            </div>
            <span aria-hidden className="text-muted">
              ›
            </span>
          </Card>
        </Link>

        <Card>
          <p className="text-sm font-medium">สิทธิ์ของคุณ (PDPA)</p>
          <p className="mt-2 text-sm text-muted">
            คุณขอดู แก้ไข และถอนความยินยอมได้เองทุกเมื่อ — หากต้องการลบข้อมูลก่อนกำหนด
            หรือใช้สิทธิ์อื่นตาม PDPA กรุณาติดต่อผู้ดูแลชมรม
          </p>
        </Card>
      </div>
    </>
  );
}
