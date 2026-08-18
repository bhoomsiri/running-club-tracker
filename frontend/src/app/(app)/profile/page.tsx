import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Badge, Card } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { getMySummary } from "@/lib/me";
import { formatDecimal } from "@/lib/format";
import { ROLE_LABELS } from "@/lib/roles";
import type { MemberProfile } from "@/lib/types";

import { EditProfile } from "./edit-profile";

export default async function ProfilePage() {
  const [summary, profile] = await Promise.all([
    getMySummary(),
    apiServer<MemberProfile>("/me/profile"),
  ]);

  return (
    <>
      <PageHeader title="โปรไฟล์" />

      <div className="space-y-4">
        <Card>
          {/* Already resolved by the backend: full_name_th when there is one. */}
          <p className="text-xl font-bold">{summary.member.name}</p>
          <p className="mt-1">
            <Badge tone={summary.member.role === "member" ? "neutral" : "brand"}>
              {ROLE_LABELS[summary.member.role]}
            </Badge>
          </p>
          <p className="mt-3 text-base text-muted tabular-nums">
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
              <p className="text-lg font-semibold">ข้อมูลสุขภาพและแบบคัดกรอง</p>
              <p className="mt-1 text-base text-muted">
                บันทึกค่าก่อน/หลังกิจกรรม แก้ไขแบบคัดกรอง และจัดการความยินยอม
              </p>
            </div>
            <span aria-hidden className="text-muted">
              ›
            </span>
          </Card>
        </Link>

        <Card>
          <p className="text-lg font-semibold">สิทธิ์ของคุณ (PDPA)</p>
          <p className="mt-2 text-base text-muted">
            คุณขอดู แก้ไข และถอนความยินยอมได้เองทุกเมื่อ — หากต้องการลบข้อมูลก่อนกำหนด
            หรือใช้สิทธิ์อื่นตาม PDPA กรุณาติดต่อผู้ดูแลชมรม
          </p>
        </Card>
      </div>
    </>
  );
}
