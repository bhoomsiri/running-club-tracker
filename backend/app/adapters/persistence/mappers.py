"""ORM <-> domain translation.

This module exists so the domain never imports SQLAlchemy. Everything below converts
in both directions and nowhere else in `adapters/` should build a domain entity by
hand — keeping it here means a schema change breaks in exactly one place.

Note the asymmetry on `to_domain`: it builds entities via their constructor, NOT via
`create()`. Rows already in the database were validated on the way in; re-running the
factory would reject legacy rows and, worse, regenerate their ids.
"""

from __future__ import annotations

from app.adapters.persistence import models
from app.domain.audit import AuditAction, AuditEntry
from app.domain.campaign import Campaign, CampaignType
from app.domain.consent import Consent, ConsentPurpose
from app.domain.entities import (
    Member,
    MemberProfile,
    MemberRole,
    ReviewStatus,
    RunEntry,
    RunSource,
    Sex,
)
from app.domain.health import HealthPhase, HealthRecord
from app.domain.redemption import (
    LedgerReason,
    PointsEntry,
    Redemption,
    RedemptionStatus,
    Reward,
)
from app.domain.screening import Screening

# --------------------------------------------------------------------------- member


def member_to_domain(row: models.Member) -> Member:
    return Member(
        id=row.id,
        clerk_user_id=row.clerk_user_id,
        display_name=row.display_name,
        role=MemberRole(row.role),
        created_at=row.created_at,
        profile=MemberProfile(
            full_name_th=row.full_name_th,
            birth_year=row.birth_year,
            sex=Sex(row.sex) if row.sex else None,
            phone=row.phone,
            emergency_contact_name=row.emergency_contact_name,
            emergency_contact_phone=row.emergency_contact_phone,
        ),
        deleted_at=row.deleted_at,
    )


def member_to_orm(member: Member) -> models.Member:
    return models.Member(
        id=member.id,
        clerk_user_id=member.clerk_user_id,
        display_name=member.display_name,
        role=member.role.value,
        created_at=member.created_at,
        deleted_at=member.deleted_at,
    )


# ------------------------------------------------------------------------- campaign


def campaign_to_domain(row: models.Campaign) -> Campaign:
    return Campaign(
        id=row.id,
        code=row.code,
        name=row.name,
        type=CampaignType(row.type),
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        config=dict(row.config),
        is_active=row.is_active,
    )


def campaign_to_orm(campaign: Campaign) -> models.Campaign:
    return models.Campaign(
        id=campaign.id,
        code=campaign.code,
        name=campaign.name,
        type=campaign.type.value,
        starts_on=campaign.starts_on,
        ends_on=campaign.ends_on,
        config=dict(campaign.config),
        is_active=campaign.is_active,
    )


# ------------------------------------------------------------------------ run entry


def run_to_domain(row: models.RunEntry) -> RunEntry:
    return RunEntry(
        id=row.id,
        member_id=row.member_id,
        distance_km=row.distance_km,
        duration_seconds=row.duration_seconds,
        run_date=row.run_date,
        evidence_key=row.evidence_key,
        evidence_sha256=row.evidence_sha256,
        source=RunSource(row.source),
        review_status=ReviewStatus(row.review_status),
        created_at=row.created_at,
    )


def run_to_orm(run: RunEntry) -> models.RunEntry:
    return models.RunEntry(
        id=run.id,
        member_id=run.member_id,
        distance_km=run.distance_km,
        duration_seconds=run.duration_seconds,
        run_date=run.run_date,
        evidence_key=run.evidence_key,
        evidence_sha256=run.evidence_sha256,
        source=run.source.value,
        review_status=run.review_status.value,
        created_at=run.created_at,
    )


# --------------------------------------------------------------- rewards & ledger


def reward_to_domain(row: models.Reward) -> Reward:
    return Reward(
        id=row.id,
        campaign_id=row.campaign_id,
        name=row.name,
        points_cost=row.points_cost,
        stock=row.stock,
        is_active=row.is_active,
    )


def reward_to_orm(reward: Reward) -> models.Reward:
    return models.Reward(
        id=reward.id,
        campaign_id=reward.campaign_id,
        name=reward.name,
        points_cost=reward.points_cost,
        stock=reward.stock,
        is_active=reward.is_active,
    )


def redemption_to_domain(row: models.Redemption) -> Redemption:
    return Redemption(
        id=row.id,
        member_id=row.member_id,
        reward_id=row.reward_id,
        campaign_id=row.campaign_id,
        points_spent=row.points_spent,
        status=RedemptionStatus(row.status),
        created_at=row.created_at,
    )


def redemption_to_orm(redemption: Redemption) -> models.Redemption:
    return models.Redemption(
        id=redemption.id,
        member_id=redemption.member_id,
        reward_id=redemption.reward_id,
        campaign_id=redemption.campaign_id,
        points_spent=redemption.points_spent,
        status=redemption.status.value,
        created_at=redemption.created_at,
    )


def points_entry_to_domain(row: models.PointsLedger) -> PointsEntry:
    return PointsEntry(
        id=row.id,
        member_id=row.member_id,
        campaign_id=row.campaign_id,
        delta=row.delta,
        reason=LedgerReason(row.reason),
        run_entry_id=row.run_entry_id,
        redemption_id=row.redemption_id,
        created_at=row.created_at,
    )


def points_entry_to_orm(entry: PointsEntry) -> models.PointsLedger:
    return models.PointsLedger(
        id=entry.id,
        member_id=entry.member_id,
        campaign_id=entry.campaign_id,
        delta=entry.delta,
        reason=entry.reason.value,
        run_entry_id=entry.run_entry_id,
        redemption_id=entry.redemption_id,
        created_at=entry.created_at,
    )


# ---------------------------------------------------------------------- health data


def health_to_domain(row: models.HealthRecord) -> HealthRecord:
    return HealthRecord(
        id=row.id,
        member_id=row.member_id,
        campaign_id=row.campaign_id,
        phase=HealthPhase(row.phase),
        measured_on=row.measured_on,
        weight_kg=row.weight_kg,
        height_cm=row.height_cm,
        resting_hr=row.resting_hr,
        systolic=row.systolic,
        diastolic=row.diastolic,
        retention_until=row.retention_until,
        created_at=row.created_at,
    )


def consent_to_domain(row: models.Consent) -> Consent:
    return Consent(
        id=row.id,
        member_id=row.member_id,
        purpose=ConsentPurpose(row.purpose),
        version=row.version,
        granted_at=row.granted_at,
        withdrawn_at=row.withdrawn_at,
    )


def consent_to_orm(consent: Consent) -> models.Consent:
    return models.Consent(
        id=consent.id,
        member_id=consent.member_id,
        purpose=consent.purpose.value,
        version=consent.version,
        granted_at=consent.granted_at,
        withdrawn_at=consent.withdrawn_at,
    )


def audit_to_domain(row: models.AuditLog) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        actor_member_id=row.actor_member_id,
        action=AuditAction(row.action),
        subject_member_id=row.subject_member_id,
        detail=dict(row.detail),  # type: ignore[arg-type]
        created_at=row.created_at,
    )


def audit_to_orm(entry: AuditEntry) -> models.AuditLog:
    return models.AuditLog(
        id=entry.id,
        actor_member_id=entry.actor_member_id,
        action=entry.action.value,
        subject_member_id=entry.subject_member_id,
        detail=dict(entry.detail),
        created_at=entry.created_at,
    )


def health_to_orm(record: HealthRecord) -> models.HealthRecord:
    return models.HealthRecord(
        id=record.id,
        member_id=record.member_id,
        campaign_id=record.campaign_id,
        phase=record.phase.value,
        measured_on=record.measured_on,
        weight_kg=record.weight_kg,
        height_cm=record.height_cm,
        resting_hr=record.resting_hr,
        systolic=record.systolic,
        diastolic=record.diastolic,
        retention_until=record.retention_until,
        created_at=record.created_at,
    )


def screening_to_domain(row: models.Screening) -> Screening:
    return Screening(
        id=row.id,
        member_id=row.member_id,
        version=row.version,
        answers=dict(row.answers),
        risk_acknowledged=row.risk_acknowledged,
        screened_on=row.screened_on,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def screening_to_orm(screening: Screening) -> models.Screening:
    return models.Screening(
        id=screening.id,
        member_id=screening.member_id,
        version=screening.version,
        answers=dict(screening.answers),
        risk_acknowledged=screening.risk_acknowledged,
        screened_on=screening.screened_on,
        created_at=screening.created_at,
        updated_at=screening.updated_at,
    )
