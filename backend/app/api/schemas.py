"""Request/response DTOs.

Separate from domain entities on purpose: the wire format can change without touching
business rules, and only what is listed here can ever reach a client.

Note every money-like number is `Decimal`, which Pydantic serialises as a JSON string.
That is deliberate (golden rule #6): a float would round distances and points on the way
out, and the frontend would display a number the ledger doesn't agree with.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.application.ports.run_extractor import RunDraft
from app.application.use_cases.get_my_summary import CampaignSummary, MemberSummary
from app.application.use_cases.get_onboarding_status import OnboardingStatus
from app.application.use_cases.list_rewards import CampaignRewards
from app.application.use_cases.list_runs import RunWithEvidence
from app.application.use_cases.view_member_health import MemberHealthView
from app.domain.campaign import Campaign, CampaignType
from app.domain.consent import Consent
from app.domain.entities import Member, ReviewStatus, RunEntry, RunSource, Sex
from app.domain.health import HealthComparison, HealthPhase, HealthRecord
from app.domain.redemption import Redemption, Reward
from app.domain.screening import Screening


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    role: str

    @classmethod
    def from_entity(cls, member: Member) -> MemberResponse:
        # No email, no clerk_user_id: the client already knows who it is, and neither
        # belongs in a response body.
        return cls(id=member.id, display_name=member.display_name, role=member.role.value)


class CampaignProgressResponse(BaseModel):
    campaign_id: UUID
    code: str
    name: str
    value: Decimal
    unit: str
    target: Decimal | None
    percent: Decimal | None
    completed: bool
    points_balance: Decimal | None

    @classmethod
    def from_summary(cls, summary: CampaignSummary) -> CampaignProgressResponse:
        return cls(
            campaign_id=summary.campaign.id,
            code=summary.campaign.code,
            name=summary.campaign.name,
            value=summary.progress.value,
            unit=summary.progress.unit,
            target=summary.progress.target,
            percent=summary.progress.percent,
            completed=summary.progress.completed,
            points_balance=summary.points_balance,
        )


class RedemptionResponse(BaseModel):
    id: UUID
    reward_id: UUID
    campaign_id: UUID
    points_spent: Decimal
    status: str
    created_at: datetime

    @classmethod
    def from_entity(cls, redemption: Redemption) -> RedemptionResponse:
        return cls(
            id=redemption.id,
            reward_id=redemption.reward_id,
            campaign_id=redemption.campaign_id,
            points_spent=redemption.points_spent,
            status=redemption.status.value,
            created_at=redemption.created_at,
        )


class HealthRecordResponse(BaseModel):
    phase: str
    measured_on: date
    weight_kg: Decimal | None
    height_cm: Decimal | None
    resting_hr: int | None
    systolic: int | None
    diastolic: int | None

    @classmethod
    def from_entity(cls, record: HealthRecord) -> HealthRecordResponse:
        return cls(
            phase=record.phase.value,
            measured_on=record.measured_on,
            weight_kg=record.weight_kg,
            height_cm=record.height_cm,
            resting_hr=record.resting_hr,
            systolic=record.systolic,
            diastolic=record.diastolic,
        )


class HealthComparisonResponse(BaseModel):
    campaign_id: UUID
    before: HealthRecordResponse | None
    after: HealthRecordResponse | None
    bmi_before: Decimal | None
    bmi_after: Decimal | None
    bmi_delta: Decimal | None

    @classmethod
    def from_comparison(cls, comparison: HealthComparison) -> HealthComparisonResponse:
        return cls(
            campaign_id=comparison.campaign_id,
            before=(
                HealthRecordResponse.from_entity(comparison.before)
                if comparison.before
                else None
            ),
            after=(
                HealthRecordResponse.from_entity(comparison.after) if comparison.after else None
            ),
            bmi_before=comparison.bmi_before,
            bmi_after=comparison.bmi_after,
            bmi_delta=comparison.bmi_delta,
        )


class MemberSummaryResponse(BaseModel):
    member: MemberResponse
    total_distance_km: Decimal
    campaigns: list[CampaignProgressResponse]
    redemptions: list[RedemptionResponse]
    health: list[HealthComparisonResponse]

    @classmethod
    def from_summary(cls, summary: MemberSummary) -> MemberSummaryResponse:
        return cls(
            member=MemberResponse.from_entity(summary.member),
            total_distance_km=summary.total_distance_km,
            campaigns=[CampaignProgressResponse.from_summary(c) for c in summary.campaigns],
            redemptions=[RedemptionResponse.from_entity(r) for r in summary.redemptions],
            health=[HealthComparisonResponse.from_comparison(h) for h in summary.health],
        )


class MemberHealthResponse(BaseModel):
    subject: MemberResponse
    health: list[HealthComparisonResponse]

    @classmethod
    def from_view(cls, view: MemberHealthView) -> MemberHealthResponse:
        return cls(
            subject=MemberResponse.from_entity(view.subject),
            health=[HealthComparisonResponse.from_comparison(h) for h in view.health],
        )


class ConsentResponse(BaseModel):
    purpose: str
    version: str
    granted_at: datetime
    withdrawn_at: datetime | None
    active: bool

    @classmethod
    def from_entity(cls, consent: Consent, current_version: str) -> ConsentResponse:
        return cls(
            purpose=consent.purpose.value,
            version=consent.version,
            granted_at=consent.granted_at,
            withdrawn_at=consent.withdrawn_at,
            active=consent.is_active(current_version),
        )


class SaveHealthRequest(BaseModel):
    """Note what is NOT here: member_id. It comes from the verified token, so a client
    cannot write to somebody else's record by putting their id in the body."""

    campaign_id: UUID
    phase: HealthPhase
    measured_on: date
    weight_kg: Decimal | None = Field(default=None, gt=0, lt=400)
    height_cm: Decimal | None = Field(default=None, ge=80, le=250)
    resting_hr: int | None = Field(default=None, ge=20, le=250)
    systolic: int | None = Field(default=None, ge=50, le=300)
    diastolic: int | None = Field(default=None, ge=30, le=200)


class EvidenceResponse(BaseModel):
    image_key: str
    sha256: str


class ExtractRequest(BaseModel):
    image_key: str


class ExtractResultResponse(BaseModel):
    """A draft for the member to confirm — never a saved value.

    `warnings` and a low `confidence` are what the UI uses to tell the member to
    double-check the numbers the app read.
    """

    draft: RunDraftResponse
    confidence: Decimal
    warnings: list[str]

    @classmethod
    def from_draft(cls, draft: RunDraft) -> ExtractResultResponse:
        return cls(
            draft=RunDraftResponse(
                distance_km=draft.distance_km,
                duration_seconds=draft.duration_seconds,
                run_date=draft.run_date,
            ),
            confidence=draft.confidence,
            warnings=draft.warnings,
        )


class RunDraftResponse(BaseModel):
    # All optional: an unreadable field comes back as null, never a guess.
    distance_km: Decimal | None
    duration_seconds: int | None
    run_date: date | None


class SubmitRunRequest(BaseModel):
    """No member_id: the run is always the caller's own. No sha256 either — it is
    derived from image_key, so a client cannot supply a hash that dodges duplicate
    detection."""

    distance_km: Decimal
    duration_seconds: int
    run_date: date
    image_key: str
    source: RunSource


class RunResponse(BaseModel):
    id: UUID
    distance_km: Decimal
    duration_seconds: int
    run_date: date
    source: str
    review_status: str
    created_at: datetime

    @classmethod
    def from_entity(cls, run: RunEntry) -> RunResponse:
        # evidence_key is not exposed: images are reached only through a presigned URL.
        return cls(
            id=run.id,
            distance_km=run.distance_km,
            duration_seconds=run.duration_seconds,
            run_date=run.run_date,
            source=run.source.value,
            review_status=run.review_status.value,
            created_at=run.created_at,
        )


class RunWithEvidenceResponse(BaseModel):
    run: RunResponse
    # Short-lived and minted per request; never a permanent object URL.
    evidence_url: str

    @classmethod
    def from_result(cls, result: RunWithEvidence) -> RunWithEvidenceResponse:
        return cls(
            run=RunResponse.from_entity(result.run), evidence_url=result.evidence_url
        )


class RewardResponse(BaseModel):
    id: UUID
    name: str
    points_cost: Decimal
    stock: int
    # Computed against the member's own balance so the UI doesn't recompute affordability
    # from two numbers it might have fetched at different times.
    can_redeem: bool

    @classmethod
    def from_entity(cls, reward: Reward, balance: Decimal) -> RewardResponse:
        return cls(
            id=reward.id,
            name=reward.name,
            points_cost=reward.points_cost,
            stock=reward.stock,
            can_redeem=reward.stock > 0 and balance >= reward.points_cost,
        )


class CampaignRewardsResponse(BaseModel):
    campaign_id: UUID
    code: str
    name: str
    points_balance: Decimal
    rewards: list[RewardResponse]

    @classmethod
    def from_catalogue(cls, catalogue: CampaignRewards) -> CampaignRewardsResponse:
        return cls(
            campaign_id=catalogue.campaign.id,
            code=catalogue.campaign.code,
            name=catalogue.campaign.name,
            points_balance=catalogue.points_balance,
            rewards=[
                RewardResponse.from_entity(r, catalogue.points_balance)
                for r in catalogue.rewards
            ],
        )


class ReviewRunRequest(BaseModel):
    decision: ReviewStatus


class CreateCampaignRequest(BaseModel):
    code: str
    name: str
    type: CampaignType
    starts_on: date
    ends_on: date
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateCampaignRequest(BaseModel):
    # `type` and `code` are absent on purpose: changing either would reinterpret the
    # runs already submitted against this campaign.
    name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class CampaignResponse(BaseModel):
    id: UUID
    code: str
    name: str
    type: str
    starts_on: date
    ends_on: date
    config: dict[str, Any]
    is_active: bool

    @classmethod
    def from_entity(cls, campaign: Campaign) -> CampaignResponse:
        return cls(
            id=campaign.id, code=campaign.code, name=campaign.name,
            type=campaign.type.value, starts_on=campaign.starts_on,
            ends_on=campaign.ends_on, config=dict(campaign.config),
            is_active=campaign.is_active,
        )


class CreateRewardRequest(BaseModel):
    campaign_id: UUID
    name: str
    points_cost: Decimal = Field(gt=0)
    stock: int = Field(ge=0)


class UpdateRewardRequest(BaseModel):
    name: str | None = None
    points_cost: Decimal | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    # Retiring a reward is how one is removed; it is never deleted.
    is_active: bool | None = None


class AdminRewardResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    name: str
    points_cost: Decimal
    stock: int
    is_active: bool

    @classmethod
    def from_entity(cls, reward: Reward) -> AdminRewardResponse:
        return cls(
            id=reward.id, campaign_id=reward.campaign_id, name=reward.name,
            points_cost=reward.points_cost, stock=reward.stock, is_active=reward.is_active,
        )


class ErrorResponse(BaseModel):
    detail: str


# ------------------------------------------------------------- profile & onboarding


class UpdateProfileRequest(BaseModel):
    """No member_id: the profile is always the caller's own. No role either — that is
    written by the verified webhook, never by a client."""

    full_name_th: str = Field(min_length=1, max_length=200)
    birth_year: int
    sex: Sex
    phone: str = Field(min_length=9, max_length=16)
    emergency_contact_name: str = Field(min_length=1, max_length=200)
    emergency_contact_phone: str = Field(min_length=9, max_length=16)


class MemberProfileResponse(BaseModel):
    """The caller's own profile.

    Sensitive: `sex` and the emergency contact are personal data the club holds for
    safety, not for display. This shape is returned to the member themselves and to an
    audited admin path — never from the plain admin member list.
    """

    full_name_th: str | None
    birth_year: int | None
    sex: str | None
    phone: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    complete: bool

    @classmethod
    def from_entity(cls, member: Member) -> MemberProfileResponse:
        profile = member.profile
        return cls(
            full_name_th=profile.full_name_th,
            birth_year=profile.birth_year,
            sex=profile.sex.value if profile.sex else None,
            phone=profile.phone,
            emergency_contact_name=profile.emergency_contact_name,
            emergency_contact_phone=profile.emergency_contact_phone,
            complete=profile.is_complete,
        )


class OnboardingStatusResponse(BaseModel):
    complete: bool
    # Named steps, in the order the wizard asks for them.
    missing: list[str]

    @classmethod
    def from_status(cls, status: OnboardingStatus) -> OnboardingStatusResponse:
        return cls(complete=status.complete, missing=list(status.missing))


# ------------------------------------------------------------------------ screening


class SaveScreeningRequest(BaseModel):
    """No member_id. `answers` must carry all eleven questions — the domain rejects a
    partial set rather than reading a missing answer as "no"."""

    answers: dict[str, bool]
    risk_acknowledged: bool
    screened_on: date


class ScreeningResponse(BaseModel):
    version: str
    answers: dict[str, bool]
    risk_acknowledged: bool
    screened_on: date
    updated_at: datetime
    # Derived, so the UI does not decide for itself what counts as a risk.
    needs_medical_advice: bool

    @classmethod
    def from_entity(cls, screening: Screening) -> ScreeningResponse:
        return cls(
            version=screening.version,
            answers=dict(screening.answers),
            risk_acknowledged=screening.risk_acknowledged,
            screened_on=screening.screened_on,
            updated_at=screening.updated_at,
            needs_medical_advice=screening.needs_medical_advice,
        )
