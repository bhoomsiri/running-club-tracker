import Link from "next/link";
import { UserButton } from "@clerk/nextjs";

import { apiServer } from "@/lib/api-server";
import { isSuperuser } from "@/lib/roles";
import type { MemberSummary } from "@/lib/types";

/**
 * Its own shell: the admin screens are not part of the member navigation.
 *
 * The nav is filtered by role. An admin works from the member list — reading a member's
 * page, deciding their runs — while what the club *offers* stays with the superuser, so
 * showing a helper four links that all answer 403 would be worse than showing none.
 * Filtering here is presentation; the backend refuses each of those endpoints regardless,
 * and each page checks again before it renders.
 */

const SECTIONS = [
  { href: "/admin", label: "ภาพรวม", superuserOnly: false },
  { href: "/admin/redemptions", label: "คิวของรางวัล", superuserOnly: true },
  { href: "/admin/announcements", label: "ข่าวประชาสัมพันธ์", superuserOnly: true },
  { href: "/admin/rewards", label: "จัดการรางวัล", superuserOnly: true },
  { href: "/admin/campaigns", label: "จัดการกิจกรรม", superuserOnly: true },
];

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const summary = await apiServer<MemberSummary>("/me/summary");
  const boss = isSuperuser(summary.member.role);
  const sections = SECTIONS.filter((section) => boss || !section.superuserOnly);

  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <div className="flex items-baseline gap-3">
            <span className="text-lg font-bold">ชมรมวิ่ง</span>
            <span className="text-base text-muted">{boss ? "ผู้ดูแลระบบ" : "ผู้ดูแล"}</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-base text-muted underline">
              กลับหน้าสมาชิก
            </Link>
            <UserButton />
          </div>
        </div>

        <nav className="mx-auto flex max-w-4xl gap-1 overflow-x-auto px-4 pb-2">
          {sections.map((section) => (
            <Link
              key={section.href}
              href={section.href}
              className="tap shrink-0 rounded-control px-3 text-base font-medium text-muted hover:bg-surface"
            >
              {section.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
