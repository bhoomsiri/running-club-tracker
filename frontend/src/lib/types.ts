/**
 * Mirrors backend/app/api/schemas.py. Keep the two in step — if a shape here disagrees
 * with the DTO, fix the DTO rather than reshaping on the client.
 *
 * Every money-like number arrives as a STRING, not a number. The backend uses Decimal
 * for distance, points and costs on purpose (rounding a distance would corrupt what a
 * member has earned) and Pydantic serialises Decimal as a JSON string. Parsing them to
 * float here would throw that away, so they stay strings and are formatted for display.
 */

export type Role = "member" | "admin" | "superuser";

export type Member = {
  id: string;
  display_name: string;
  role: Role;
};

export type CampaignProgress = {
  campaign_id: string;
  code: string;
  name: string;
  value: string;
  unit: string;
  target: string | null;
  percent: string | null;
  completed: boolean;
  points_balance: string | null;
};

export type RedemptionStatus = "pending" | "fulfilled" | "cancelled";

export type Redemption = {
  id: string;
  reward_id: string;
  campaign_id: string;
  points_spent: string;
  status: RedemptionStatus;
  created_at: string;
};

export type HealthPhase = "before" | "after";

export type HealthRecord = {
  phase: HealthPhase;
  measured_on: string;
  weight_kg: string | null;
  height_cm: string | null;
  resting_hr: number | null;
  systolic: number | null;
  diastolic: number | null;
};

export type HealthComparison = {
  campaign_id: string;
  before: HealthRecord | null;
  after: HealthRecord | null;
  bmi_before: string | null;
  bmi_after: string | null;
  bmi_delta: string | null;
};

export type MemberSummary = {
  member: Member;
  total_distance_km: string;
  campaigns: CampaignProgress[];
  redemptions: Redemption[];
  health: HealthComparison[];
};

export type Consent = {
  purpose: string;
  version: string;
  granted_at: string;
  withdrawn_at: string | null;
  active: boolean;
};

export type RunSource = "app_screenshot" | "manual_photo";
export type ReviewStatus = "pending" | "approved" | "rejected";

export type Run = {
  id: string;
  distance_km: string;
  duration_seconds: number;
  run_date: string;
  source: RunSource;
  review_status: ReviewStatus;
  created_at: string;
};

export type RunWithEvidence = {
  run: Run;
  /** Presigned and short-lived — fetch it again rather than storing it. */
  evidence_url: string;
};

export type EvidenceUpload = {
  image_key: string;
};

/** What the AI read. A draft to fill the form with — never something to submit as-is. */
export type RunDraft = {
  distance_km: string | null;
  duration_seconds: number | null;
  run_date: string | null;
};

export type ExtractResult = {
  draft: RunDraft;
  confidence: string;
  warnings: string[];
};

export type SubmitRunRequest = {
  distance_km: string;
  duration_seconds: number;
  run_date: string;
  image_key: string;
  source: RunSource;
  /** Absent on purpose: member_id. The backend takes it from the verified token. */
};

export type Reward = {
  id: string;
  name: string;
  points_cost: string;
  stock: number;
  /** Computed by the backend against this member's balance — don't recompute it. */
  can_redeem: boolean;
};

export type CampaignRewards = {
  campaign_id: string;
  code: string;
  name: string;
  points_balance: string;
  rewards: Reward[];
};
