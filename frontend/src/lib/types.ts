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
  /** What to show: full_name_th once given, else display_name. Use this everywhere. */
  name: string;
  /** What Clerk holds. Kept because the two can differ; rarely the one to display. */
  display_name: string;
  role: Role;
  /** Job and unit at the hospital. Ordinary personal data, unlike the rest of the
   * profile — which is why these two travel without an audit row. */
  position: string | null;
  department: string | null;
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
  /** False both for a withdrawn consent and for one given to wording that has since
   * changed. This is the only field the health form should gate on. */
  active: boolean;
};

export type SaveHealthRequest = {
  campaign_id: string;
  phase: HealthPhase;
  measured_on: string;
  weight_kg?: string;
  height_cm?: string;
  resting_hr?: number;
  systolic?: number;
  diastolic?: number;
  /** Absent on purpose: member_id. The backend takes it from the verified token. */
};

export type RunSource = "app_screenshot" | "manual_photo";
/** Matches app/domain/entities.py exactly. "flagged" means awaiting a decision — a
 * flagged run still counts toward progress; only "rejected" earns nothing. */
export type ReviewStatus = "ok" | "flagged" | "rejected";

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
  /** Of the scrubbed bytes, computed by the backend. Never sent back on submit — the
   * key is what identifies the image, so a client cannot supply a hash that would slip
   * past duplicate detection. */
  sha256: string;
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
  /** Presigned and short-lived, minted for this response. Render it now; never store it. */
  image_url: string | null;
};

export type CampaignRewards = {
  campaign_id: string;
  code: string;
  name: string;
  points_balance: string;
  rewards: Reward[];
};

/** One line of the club standing. Every member sees every one of these, so it holds a
 * name, a distance and two counts — and nothing else about anybody. */
export type LeaderboardEntry = {
  rank: number;
  member_id: string;
  name: string;
  total_distance_km: string;
  /** Balance in the campaign that awards points, or null when none does. */
  points: string | null;
  run_count: number;
};

export type Leaderboard = {
  entries: LeaderboardEntry[];
  /** The caller's own line, always — so someone far down the list is still told where
   * they are instead of searching for themselves. */
  me: LeaderboardEntry;
  total_members: number;
  /** What the points column is counting, so the UI labels it rather than guesses. */
  points_campaign_name: string | null;
};

/** Club news. The only shape in this file that arrives without a session — the landing
 * page is for people who have not signed up yet. Note what it does not carry: no author,
 * no member id. */
export type Announcement = {
  id: string;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
};

/** The superuser's view: the same notice plus whether anyone else can see it. */
export type AdminAnnouncement = Announcement & {
  is_published: boolean;
};

export type Sex = "male" | "female";

/** The finisher shirt sizes, exactly as the backend's `ShirtSize` spells them. Anything
 * else is a 422 — see lib/shirt-sizes.ts for the list and the measurements. */
export type ShirtSize = "XS" | "S" | "M" | "L" | "XL" | "2XL" | "3XL" | "4XL" | "5XL";

export type MemberProfile = {
  full_name_th: string | null;
  birth_year: number | null;
  sex: Sex | null;
  position: string | null;
  department: string | null;
  shirt_size: ShirtSize | null;
  phone: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  complete: boolean;
};

export type UpdateProfileRequest = {
  full_name_th: string;
  birth_year: number;
  sex: Sex;
  position: string;
  department: string;
  shirt_size: ShirtSize;
  phone: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
};

/** The steps the wizard walks, in the order the backend reports them. */
export type OnboardingStep = "consent" | "profile" | "screening" | "baseline";

export type OnboardingStatus = {
  complete: boolean;
  missing: OnboardingStep[];
};

export type Screening = {
  version: string;
  /** All eleven questions; a partial set is refused by the backend. */
  answers: Record<string, boolean>;
  risk_acknowledged: boolean;
  screened_on: string;
  updated_at: string;
  /** Derived by the backend, so the UI never decides for itself what counts as a risk. */
  needs_medical_advice: boolean;
};

/** One member's standing in the club-wide table.
 *
 * Note what is not here: health, screening, sex, phone, emergency contact. Reading those
 * is an audited act about one named member, so they arrive through a drill-down and
 * never through this list. */
export type MemberOverview = {
  member_id: string;
  /** full_name_th when the member has given one, else their Clerk display name. */
  name: string;
  role: Role;
  /** The one profile field in this list, and only because it is not sensitive. */
  department: string | null;
  total_distance_km: string;
  run_count: number;
  pending_review_count: number;
  campaigns: CampaignProgress[];
};

export type Campaign = {
  id: string;
  code: string;
  name: string;
  type: string;
  starts_on: string;
  ends_on: string;
  config: Record<string, unknown>;
  is_active: boolean;
};

export type ClubOverview = {
  campaigns: Campaign[];
  members: MemberOverview[];
};

export type MemberProgress = {
  member: Member;
  total_distance_km: string;
  run_count: number;
  pending_review_count: number;
  campaigns: CampaignProgress[];
  redemptions: Redemption[];
};

/** Sensitive. Only ever arrives from the audited endpoint, one member at a time. */
export type MemberContact = {
  subject: Member;
  birth_year: number | null;
  sex: Sex | null;
  phone: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
};

/** Sensitive, audited. */
export type MemberScreening = {
  subject: Member;
  screening: Screening | null;
};

/** Sensitive, audited. */
export type MemberHealth = {
  subject: Member;
  health: HealthComparison[];
};

/** What POST /admin/runs/{id}/review accepts — the same three values. */
export type ReviewDecision = ReviewStatus;

export type AdminReward = {
  id: string;
  campaign_id: string;
  name: string;
  points_cost: string;
  stock: number;
  is_active: boolean;
  image_url: string | null;
};

/** What POST /admin/rewards/image returns: where the photo landed. Attaching it to a
 * reward is the separate call that follows. */
export type RewardImageUpload = {
  image_key: string;
};

/** Why a redemption cannot be handed over yet — the same two checks the fulfil endpoint
 * makes. null means it can. */
export type FulfilBlock = "negative_balance" | "unresolved_runs";

export type PendingRedemption = {
  redemption: Redemption;
  member_name: string;
  reward_name: string;
  balance: string;
  blocked_by: FulfilBlock | null;
};
