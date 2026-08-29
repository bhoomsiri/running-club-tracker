"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The primary navigation on anything narrower than a desktop. At the bottom because
 * members are on phones one-handed, and it moves to the top on wider screens where a
 * thumb bar makes no sense.
 *
 * From `lg` up the collapsible rail takes over and this is hidden. The two are not the
 * same list: the rail carries ข่าวประชาสัมพันธ์ and the admin link as well, because a
 * desktop has the room for them. Five is the most that fits across a phone without the
 * targets shrinking below the 48px floor, and these are the five a member on a phone
 * actually reaches for.
 */
const ITEMS = [
  { href: "/dashboard", label: "แดชบอร์ด", icon: "📊" },
  { href: "/submit", label: "ส่งผลวิ่ง", icon: "🏃" },
  { href: "/runs", label: "ผลวิ่ง", icon: "📋" },
  { href: "/rewards", label: "รางวัล", icon: "🎁" },
  { href: "/profile", label: "โปรไฟล์", icon: "👤" },
] as const;

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="เมนูหลัก"
      className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-background pb-[env(safe-area-inset-bottom)] sm:static sm:border-t-0 sm:border-b sm:pb-0 lg:hidden"
    >
      <ul className="mx-auto flex max-w-3xl">
        {ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 flex-col items-center justify-center gap-0.5 px-1 py-2 text-xs sm:min-h-12 sm:flex-row sm:gap-2 sm:text-base ${
                  active ? "font-semibold text-brand" : "font-medium text-muted"
                }`}
              >
                <span aria-hidden className="text-xl sm:text-lg">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
