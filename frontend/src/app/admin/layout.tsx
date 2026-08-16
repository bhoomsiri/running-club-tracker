import Link from "next/link";
import { UserButton } from "@clerk/nextjs";

const SECTIONS = [
  { href: "/admin", label: "ภาพรวม" },
  { href: "/admin/redemptions", label: "คิวของรางวัล" },
  { href: "/admin/announcements", label: "ข่าวประชาสัมพันธ์" },
  { href: "/admin/rewards", label: "จัดการรางวัล" },
  { href: "/admin/campaigns", label: "จัดการกิจกรรม" },
];

/** Its own shell: the admin screens are not part of the member navigation. */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          <div className="flex items-baseline gap-3">
            <span className="font-semibold">ชมรมวิ่ง</span>
            <span className="text-sm text-muted">ผู้ดูแลระบบ</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-sm text-muted underline">
              กลับหน้าสมาชิก
            </Link>
            <UserButton />
          </div>
        </div>

        <nav className="mx-auto flex max-w-4xl gap-1 overflow-x-auto px-4 pb-2">
          {SECTIONS.map((section) => (
            <Link
              key={section.href}
              href={section.href}
              className="shrink-0 rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-surface"
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
