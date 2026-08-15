import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { Badge, Card } from "@/components/ui";
import { apiServer } from "@/lib/api-server";
import { formatDecimal } from "@/lib/format";
import type { MemberSummary, Role } from "@/lib/types";

const ROLE_LABELS: Record<Role, string> = {
  member: "สมาชิก",
  admin: "ผู้ดูแล",
  superuser: "ผู้ดูแลระบบ",
};

export default async function ProfilePage() {
  const summary = await apiServer<MemberSummary>("/me/summary");

  return (
    <>
      <PageHeader title="โปรไฟล์" />

      <div className="space-y-4">
        <Card>
          <p className="text-lg font-medium">{summary.member.display_name}</p>
          <p className="mt-1">
            <Badge tone={summary.member.role === "member" ? "neutral" : "brand"}>
              {ROLE_LABELS[summary.member.role]}
            </Badge>
          </p>
          <p className="mt-3 text-sm text-muted tabular-nums">
            ระยะสะสมรวม {formatDecimal(summary.total_distance_km)} กม.
          </p>
        </Card>

        {/* Health lives on its own screen rather than inline here: it is behind a
            consent gate, and mixing it into a general profile page makes it look like
            just another field to fill in. */}
        <Link href="/health" className="block">
          <Card className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">ข้อมูลสุขภาพ</p>
              <p className="mt-0.5 text-sm text-muted">
                บันทึกค่าก่อน/หลังกิจกรรม และจัดการความยินยอม
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
            คุณขอดู แก้ไข ถอนความยินยอม หรือขอลบข้อมูลสุขภาพของคุณได้ทุกเมื่อ —
            การถอนความยินยอมทำได้เองที่หน้าข้อมูลสุขภาพ ส่วนการขอลบข้อมูล
            กรุณาติดต่อผู้ดูแลชมรม
          </p>
        </Card>
      </div>
    </>
  );
}
