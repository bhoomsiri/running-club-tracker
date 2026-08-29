import { UserButton } from "@clerk/nextjs";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
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
 * The chrome itself is `AppShell`, which is a client component because a collapsing rail
 * and a drawer are state. Everything that needs the session stays here on the server —
 * the onboarding gate, the role, and Clerk's own `UserButton` — and is passed down, so
 * the client half never learns anything the markup would not already have shown.
 *
 * The admin link lives in the rail under its own divider, not at the bottom of the
 * dashboard where it started: staff reach for it from wherever they happen to be, and a
 * link you have to scroll past your own redemptions to find is one you navigate by URL
 * instead. It is navigation — /admin checks the role again and the backend refuses
 * regardless.
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
    <AppShell isStaff={isStaff(summary.member.role)} account={<UserButton />}>
      {children}
    </AppShell>
  );
}
