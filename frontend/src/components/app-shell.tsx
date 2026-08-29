"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

import { BottomNav } from "@/components/bottom-nav";

/**
 * The shell every signed-in screen sits in.
 *
 * **Two navigations, split by screen, not one navigation that transforms.** From `lg` up
 * there is a rail that collapses to icons. Below it there is the bottom tab bar the app
 * has always had — members are on phones, one-handed, and a thumb bar is within reach
 * where a hamburger in the top-left corner is not. A drawer would have been one
 * component instead of two, and it would have moved the primary navigation of a
 * phone-first app to the far corner of the screen to save that.
 *
 * **ส่งผลวิ่ง is the primary action**, a filled button in the rail rather than another
 * grey row, and the middle tab on a phone. Submitting a run is the only thing most
 * members open the app to do.
 *
 * **The admin link is separate**, under its own divider in the rail and beside the
 * avatar on a phone — never mixed into the member tabs. It goes to /admin, which has its
 * own layout and its own menu. Navigation only: /admin checks the role again and the
 * backend refuses regardless.
 */

type Item = { href: string; label: string; icon: React.ReactNode };

/**
 * The rail's list. Longer than the phone's five tabs on purpose — a desktop has the room
 * for ข่าวประชาสัมพันธ์, and BottomNav's five are what fit across a phone at 48px each.
 */
const ITEMS: Item[] = [
  { href: "/dashboard", label: "แดชบอร์ด", icon: <IconGrid /> },
  { href: "/runs", label: "ผลวิ่ง", icon: <IconList /> },
  { href: "/announcements", label: "ข่าวประชาสัมพันธ์", icon: <IconMegaphone /> },
  { href: "/rewards", label: "รางวัล", icon: <IconGift /> },
  { href: "/profile", label: "โปรไฟล์", icon: <IconUser /> },
];

const SUBMIT: Item = { href: "/submit", label: "ส่งผลวิ่ง", icon: <IconUpload /> };

const COLLAPSED_KEY = "runclub:rail-collapsed";
const COLLAPSED_EVENT = "runclub:rail-collapsed-changed";

/**
 * The collapse preference lives in localStorage, which makes it an external store rather
 * than React state — so it is read through `useSyncExternalStore`, the hook built for
 * exactly that. Reading it in an effect and calling setState would work and is what this
 * started as, but it renders once with the wrong rail and then again with the right one;
 * the server snapshot below is what lets React reconcile it in one pass instead.
 *
 * Every failure mode falls back to expanded: private browsing, storage switched off, a
 * value somebody edited by hand. A rail showing its labels is the safe wrong answer.
 */
const collapsedStore = {
  subscribe(onChange: () => void) {
    window.addEventListener(COLLAPSED_EVENT, onChange);
    // Another tab changing it counts too — the same person, the same preference.
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener(COLLAPSED_EVENT, onChange);
      window.removeEventListener("storage", onChange);
    };
  },
  get(): boolean {
    try {
      return window.localStorage.getItem(COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  },
  set(collapsed: boolean) {
    try {
      window.localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      // Not being able to remember it is no reason to refuse to do it.
    }
    window.dispatchEvent(new Event(COLLAPSED_EVENT));
  },
};

/** There is no rail on the server, and no preference to read. */
const collapsedOnServer = () => false;

/**
 * Screens that lay out in columns and need the room. Everything else keeps the reading
 * width the app has always had — a paragraph or a form stretched across a 27" monitor is
 * harder to read, not easier, and widening `main` for everyone would quietly redesign
 * every page in the app to fix one.
 */
const WIDE_ROUTES = ["/dashboard"];

export function AppShell({
  isStaff,
  account,
  children,
}: {
  isStaff: boolean;
  /** Clerk's own control, rendered on the server and passed through. */
  account: React.ReactNode;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const collapsed = useSyncExternalStore(
    collapsedStore.subscribe,
    collapsedStore.get,
    collapsedOnServer,
  );

  return (
    <div className="flex min-h-screen">
      <aside
        className={`hidden shrink-0 flex-col gap-1 border-r border-border bg-background p-3 lg:sticky lg:top-0 lg:flex lg:h-screen lg:transition-[width] ${
          collapsed ? "lg:w-[4.75rem]" : "lg:w-60"
        }`}
      >
        <div className="mb-2 flex min-h-10 items-center gap-2.5 px-1">
          <span
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-control bg-brand text-on-brand"
          >
            <IconRunner />
          </span>
          {collapsed ? null : (
            <span className="min-w-0 flex-1">
              <span className="block truncate font-bold">ชมรมวิ่ง</span>
              <span className="block truncate text-xs font-semibold text-muted">
                PTRH RunClub
              </span>
            </span>
          )}
          <button
            type="button"
            onClick={() => collapsedStore.set(!collapsed)}
            aria-label={collapsed ? "ขยายเมนู" : "ย่อเมนู"}
            className="grid size-10 shrink-0 place-items-center rounded-control text-muted hover:bg-surface hover:text-foreground"
          >
            <IconBars />
          </button>
        </div>

        <nav aria-label="เมนูหลัก" className="flex flex-1 flex-col gap-0.5">
          <RailLink item={ITEMS[0]} pathname={pathname} collapsed={collapsed} />
          <RailLink item={SUBMIT} pathname={pathname} collapsed={collapsed} primary />
          {ITEMS.slice(1).map((item) => (
            <RailLink
              key={item.href}
              item={item}
              pathname={pathname}
              collapsed={collapsed}
            />
          ))}

          {isStaff ? (
            <>
              <hr className="mx-2 my-2 border-border" />
              {collapsed ? null : (
                <p className="px-3 pb-1 text-xs font-bold tracking-wide text-muted uppercase">
                  เฉพาะแอดมิน
                </p>
              )}
              <RailLink
                item={{ href: "/admin", label: "แผงผู้ดูแล", icon: <IconShield /> }}
                pathname={pathname}
                collapsed={collapsed}
              />
            </>
          ) : null}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex min-h-14 items-center gap-3 border-b border-border bg-background/85 px-4 py-2 backdrop-blur-sm sm:px-6 lg:border-b-0">
          {/* The wordmark belongs to the rail from lg up, where the rail is showing it. */}
          <span className="font-bold lg:hidden">ชมรมวิ่ง</span>
          <span className="flex-1" />
          {/* On a phone the rail is not there to hold the admin link, and it must not go
              into the five member tabs. Beside the avatar is where it was and where staff
              already look for it. */}
          {isStaff ? (
            <Link
              href="/admin"
              className="tap shrink-0 rounded-control border border-border px-3 font-medium lg:hidden"
            >
              แผงผู้ดูแล
            </Link>
          ) : null}
          {account}
        </header>

        <BottomNav />

        {/* pb-28 clears the tab bar, which is fixed to the bottom only on phones — from
            sm it is a static row above this, and from lg it is gone. */}
        <main
          className={`mx-auto w-full min-w-0 flex-1 px-4 py-5 pb-28 sm:px-6 sm:py-6 sm:pb-8 ${
            WIDE_ROUTES.includes(pathname) ? "max-w-6xl" : "max-w-3xl"
          }`}
        >
          {children}
        </main>
      </div>
    </div>
  );
}

function RailLink({
  item,
  pathname,
  collapsed,
  primary = false,
}: {
  item: Item;
  pathname: string;
  collapsed: boolean;
  primary?: boolean;
}) {
  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
  const tone = primary
    ? "bg-brand text-on-brand font-bold"
    : active
      ? "bg-brand-tint text-brand font-semibold"
      : "text-muted hover:bg-surface hover:text-foreground font-semibold";

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      // 48px tall, like every other tap target in the app.
      title={collapsed ? item.label : undefined}
      className={`flex min-h-12 items-center gap-3 rounded-control ${tone} ${
        collapsed ? "justify-center px-0" : "px-3"
      }`}
    >
      <span aria-hidden className="shrink-0">
        {item.icon}
      </span>
      {collapsed ? null : <span className="truncate">{item.label}</span>}
    </Link>
  );
}

/* Inline SVG rather than an icon package: seven icons at 20px do not justify a
   dependency. The bottom bar keeps its emoji — they are legible at tab size and were
   chosen for it — but a rail label sitting beside one wants a stroke icon that takes the
   current colour, which emoji cannot. */

function svgProps(size = 20) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
}

function IconRunner() {
  return (
    <svg {...svgProps()}>
      <path d="M13 4l-2 5h4l-2 5" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}

function IconGrid() {
  return (
    <svg {...svgProps()}>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </svg>
  );
}

function IconUpload() {
  return (
    <svg {...svgProps()}>
      <path d="M12 15V4M8 8l4-4 4 4" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

function IconList() {
  return (
    <svg {...svgProps()}>
      <path d="M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
    </svg>
  );
}

function IconMegaphone() {
  return (
    <svg {...svgProps()}>
      <path d="M4 10v4a1 1 0 0 0 1 1h3l5 4V5L8 9H5a1 1 0 0 0-1 1z" />
      <path d="M18 9a4 4 0 0 1 0 6" />
    </svg>
  );
}

function IconGift() {
  return (
    <svg {...svgProps()}>
      <rect x="3" y="8" width="18" height="13" rx="2" />
      <path d="M3 12h18M12 8v13" />
      <path d="M12 8S9.5 3.5 7 5s1 3 5 3 7.5-1.5 5-3-5 3-5 3z" />
    </svg>
  );
}

function IconUser() {
  return (
    <svg {...svgProps()}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </svg>
  );
}

function IconShield() {
  return (
    <svg {...svgProps()}>
      <path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z" />
      <path d="M9.5 12l1.8 1.8L15 10" />
    </svg>
  );
}

function IconBars() {
  return (
    <svg {...svgProps(19)}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}
