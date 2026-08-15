import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import type {
  MemberProfile,
  MemberSummary,
  OnboardingStatus,
  Screening,
} from "@/lib/types";

import { OnboardingWizard } from "./wizard";

/**
 * Deliberately outside the (app) route group.
 *
 * The gate that sends incomplete members here lives in that group's layout, so putting
 * this page inside it would make the page redirect to itself — a loop the member could
 * not escape and could not be told about. Being a sibling instead means the gate simply
 * never runs on this route.
 *
 * It is still behind the auth proxy like everything else; only the onboarding check is
 * skipped.
 */
export default async function OnboardingPage() {
  const status = await apiServer<OnboardingStatus>("/me/onboarding");
  if (status.complete) {
    // Nothing to do — including for the superuser, whom the backend exempts.
    redirect("/dashboard");
  }

  // Fetched together so a member resuming half-finished onboarding sees what they
  // already entered rather than an empty form.
  const [profile, screening, summary] = await Promise.all([
    apiServer<MemberProfile>("/me/profile"),
    apiServer<Screening | null>("/screening"),
    apiServer<MemberSummary>("/me/summary"),
  ]);

  return (
    <>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">ยินดีต้อนรับสู่ชมรมวิ่ง</h1>
        <p className="mt-1 text-sm text-muted">
          อีกไม่กี่ขั้นตอนก็เริ่มส่งผลวิ่งได้แล้ว
        </p>
      </header>

      <OnboardingWizard
        missing={status.missing}
        profile={profile}
        screening={screening}
        campaigns={summary.campaigns}
      />
    </>
  );
}
