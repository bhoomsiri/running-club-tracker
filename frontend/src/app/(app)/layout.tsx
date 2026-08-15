import { UserButton } from "@clerk/nextjs";
import { redirect } from "next/navigation";

import { BottomNav } from "@/components/bottom-nav";
import { apiServer } from "@/lib/api-server";
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
 */
export default async function AppLayout({ children }: LayoutProps<"/">) {
  const status = await apiServer<OnboardingStatus>("/me/onboarding");
  if (!status.complete) {
    redirect("/onboarding");
  }

  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <span className="font-semibold">ชมรมวิ่ง</span>
          <UserButton />
        </div>
      </header>

      <BottomNav />

      {/* Bottom padding clears the fixed nav on phones; it is static from `sm` up. */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 pb-24 sm:pb-6">
        {children}
      </main>
    </>
  );
}
