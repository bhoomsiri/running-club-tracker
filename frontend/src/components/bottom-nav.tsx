"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * The primary navigation. At the bottom because members are on phones one-handed, and
 * it moves to the top on wider screens where a thumb bar makes no sense.
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
      className="fixed inset-x-0 bottom-0 z-10 border-t border-border bg-background pb-[env(safe-area-inset-bottom)] sm:static sm:border-t-0 sm:border-b sm:pb-0"
    >
      <ul className="mx-auto flex max-w-3xl">
        {ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex flex-col items-center gap-0.5 px-1 py-2.5 text-[11px] sm:flex-row sm:justify-center sm:gap-2 sm:py-3 sm:text-sm ${
                  active ? "font-semibold text-brand" : "text-muted"
                }`}
              >
                <span aria-hidden className="text-lg sm:text-base">
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
