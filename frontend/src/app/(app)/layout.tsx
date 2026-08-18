import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { redirect } from "next/navigation";

import { BottomNav } from "@/components/bottom-nav";
import { apiServer } from "@/lib/api-server";
import { getMySummary } from "@/lib/me";
import { isStaff } from "@/lib/roles";
import type { OnboardingStatus } from "@/lib/types";

/**
 * The signed-in shell, and the onboarding gate.
 *
 * Checked here rather than on each page so a screen added later is covered the moment it
 * exists. The check is a server-side redirect: a client-side one would render the page
 * first, which for a member who has not consented would mean showing them a screen built
 * from data the club should not yet be processing.
 *
 * /onboarding is a sibling route group, not a child of this one, so it is not gated by
 * this layout — otherwise it would redirect to itself forever.
 *
 * The superuser is exempt, decided by the backend rather than by a role check here:
 * somebody has to reach the admin screens on a fresh deployment, and that person cannot
 * be locked out by a gate they are there to configure.
 *
 * The admin link lives up here beside the avatar, not at the bottom of the dashboard
 * where it started: staff reach for it from wherever they happen to be, and a link you
 * have to scroll past your own redemptions to find is one you navigate by URL instead.
 * It is navigation — /admin checks the role again and the backend refuses regardless.
 */
export default async function AppLayout({ children }: LayoutProps<"/">) {
  const status = await apiServer<OnboardingStatus>("/me/onboarding");
  if (!status.complete) {
    redirect("/onboarding");
  }

  // After the gate, never before: a member who has not consented is redirected above
  // rather than having their summary fetched to decide what to put in a header.
  const summary = await getMySummary();

  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex min-h-14 max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <span className="text-lg font-bold">ชมรมวิ่ง</span>
          <div className="flex items-center gap-2">
            {isStaff(summary.member.role) ? (
              <Link
                href="/admin"
                className="tap shrink-0 rounded-control border border-border px-3 text-base font-medium"
              >
                แผงผู้ดูแล
              </Link>
            ) : null}
            <UserButton />
          </div>
        </div>
      </header>

      <BottomNav />

      {/* Bottom padding clears the fixed nav on phones; it is static from `sm` up. */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 pb-28 sm:pb-8">
        {children}
      </main>
    </>
  );
}
