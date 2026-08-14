"""SQLAlchemy ORM models — the persistence shape of the app.

This file lives in `adapters/` because it imports a framework. The domain never
sees these classes; `mappers.py` will convert ORM <-> domain entities.

Schema invariants worth knowing before editing (see CLAUDE.md golden rules):
  - reward-affecting numbers are `numeric`, never float
  - points balance is SUM(points_ledger.delta) — there is no cached balance column
  - run_entry has no campaign_id: campaign progress is derived by filtering runs
    into the campaign's date window at read time
  - health data lives in its own table, gated by `consent` and read-logged in `audit_log`

Edge case to respect when the erasure use case is built (PDPA right to be forgotten):
`points_ledger` references `run_entry` and `redemption` with ON DELETE RESTRICT, which
deliberately blocks deleting a run or redemption that points still hang off. That
collides with the ON DELETE CASCADE from `member`, so hard-deleting a member must
delete explicitly, in order, inside one transaction:
    points_ledger -> redemption -> run_entry -> health_record/consent/audit -> member
Never rely on a single cascade from `member` to unwind all of it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable constraint/index names so Alembic autogenerate produces clean diffs.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    # The app supplies this via the Clock port; the server default is only a backstop
    # for seeds and manual inserts.
    return mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


# --------------------------------------------------------------------------- member


class Member(Base):
    """A club member. Mirrors a Clerk user; `email` is deliberately NOT stored here
    (Clerk holds it — PDPA data minimisation, and golden rule #8 keeps it out of logs)."""

    __tablename__ = "member"

    id: Mapped[uuid.UUID] = _pk()
    clerk_user_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    # Synced from Clerk publicMetadata via the verified webhook — never from the client.
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="member")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # PDPA right to erasure: set first, hard-delete after the grace period.
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint("role IN ('member', 'admin', 'superuser')", name="role_valid"),
        # There can be only one superuser, enforced by the database rather than by
        # convention. `role` is only ever written by the verified Clerk webhook or the
        # bootstrap config (settings.superuser_clerk_user_id) — never by a client.
        sa.Index(
            "uq_member_single_superuser",
            "role",
            unique=True,
            postgresql_where=sa.text("role = 'superuser'"),
        ),
    )


# ------------------------------------------------------------------------- campaign


class Campaign(Base):
    """A yearly activity. `type` selects the CampaignPolicy; `config` holds that
    policy's parameters (e.g. {"target_km": 100} or {"km_per_point": 1})."""

    __tablename__ = "campaign"

    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    starts_on: Mapped[date] = mapped_column(sa.Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(sa.Date, nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        # Adding a campaign type next year = a new policy file, a registry line, and
        # one migration that widens this constraint. Nothing else changes.
        sa.CheckConstraint(
            "type IN ('cumulative_distance', 'redeem_reward', 'daily_threshold_reward')",
            name="type_valid",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="window_ordered"),
    )


# ------------------------------------------------------------------------ run entry


class RunEntry(Base):
    """One submitted run. Source of truth for every campaign's progress."""

    __tablename__ = "run_entry"

    id: Mapped[uuid.UUID] = _pk()
    member_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("member.id", ondelete="CASCADE"), nullable=False
    )
    distance_km: Mapped[Decimal] = mapped_column(sa.Numeric(6, 3), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    run_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # Object key in the private bucket. Served only via short-lived presigned URLs.
    evidence_key: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    # Same image re-used by ANOTHER member is flagged for a human, not auto-blocked.
    review_status: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default="ok"
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        sa.CheckConstraint("distance_km > 0 AND distance_km <= 200", name="distance_sane"),
        sa.CheckConstraint(
            "duration_seconds > 0 AND duration_seconds <= 86400", name="duration_sane"
        ),
        sa.CheckConstraint("source IN ('app_screenshot', 'manual_photo')", name="source_valid"),
        sa.CheckConstraint(
            "review_status IN ('ok', 'flagged', 'rejected')", name="review_status_valid"
        ),
        # Same member submitting the same image twice is a hard duplicate.
        sa.UniqueConstraint("member_id", "evidence_sha256", name="uq_run_entry_member_evidence"),
        # Cross-member reuse lookup + the main "my runs in a window" query.
        sa.Index("ix_run_entry_evidence_sha256", "evidence_sha256"),
        sa.Index("ix_run_entry_member_id_run_date", "member_id", "run_date"),
    )


# ------------------------------------------------------------------ rewards & ledger
# Declared before points_ledger, which references redemption.


class Reward(Base):
    __tablename__ = "reward"

    id: Mapped[uuid.UUID] = _pk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaign.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    points_cost: Mapped[Decimal] = mapped_column(sa.Numeric(12, 2), nullable=False)
    stock: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        sa.CheckConstraint("points_cost > 0", name="cost_positive"),
        # Last line of defence against overselling; the row lock in the redeem
        # transaction is the first.
        sa.CheckConstraint("stock >= 0", name="stock_non_negative"),
        sa.Index("ix_reward_campaign_id", "campaign_id"),
    )


class Redemption(Base):
    __tablename__ = "redemption"

    id: Mapped[uuid.UUID] = _pk()
    member_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("member.id", ondelete="CASCADE"), nullable=False
    )
    reward_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("reward.id", ondelete="RESTRICT"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaign.id", ondelete="RESTRICT"), nullable=False
    )
    # Snapshot of the price paid: the reward's cost may change later.
    points_spent: Mapped[Decimal] = mapped_column(sa.Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        sa.CheckConstraint("points_spent > 0", name="spent_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'fulfilled', 'cancelled')", name="status_valid"
        ),
        sa.Index("ix_redemption_member_id", "member_id"),
    )


class PointsLedger(Base):
    """Append-only. A member's balance is SUM(delta) for a campaign — never a column."""

    __tablename__ = "points_ledger"

    id: Mapped[uuid.UUID] = _pk()
    member_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("member.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaign.id", ondelete="RESTRICT"), nullable=False
    )
    delta: Mapped[Decimal] = mapped_column(sa.Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    # What caused this row, as real FKs so every point is traceable to its source.
    # RESTRICT: a run or redemption with ledger rows attached cannot just vanish.
    # (Erasure under PDPA therefore deletes in order — see the module note at the top.)
    run_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("run_entry.id", ondelete="RESTRICT")
    )
    redemption_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("redemption.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        sa.CheckConstraint(
            "reason IN ('run_earned', 'redeemed', 'adjustment', 'reversal')",
            name="reason_valid",
        ),
        # Each reason carries exactly the reference it should. adjustment/reversal may
        # point back at their source for audit, but never at both at once.
        sa.CheckConstraint(
            """
            CASE reason
              WHEN 'run_earned' THEN run_entry_id IS NOT NULL AND redemption_id IS NULL
              WHEN 'redeemed'   THEN redemption_id IS NOT NULL AND run_entry_id IS NULL
              ELSE NOT (run_entry_id IS NOT NULL AND redemption_id IS NOT NULL)
            END
            """,
            name="ref_matches_reason",
        ),
        # NOT unique (see migration 0002). Earning is reconciled, so one run can be the
        # attribution point for several rows of the same reason over its life:
        # submit -> run_earned, reject -> reversal, approve -> run_earned again.
        # Idempotency comes from reconcile writing nothing when the delta is zero, under
        # the per-account advisory lock.
        sa.Index(
            "ix_points_ledger_campaign_run_reason",
            "campaign_id",
            "run_entry_id",
            "reason",
            postgresql_where=sa.text("run_entry_id IS NOT NULL"),
        ),
        # A redemption, by contrast, really can only be charged or refunded once.
        sa.Index(
            "uq_points_ledger_redemption_reason",
            "redemption_id",
            "reason",
            unique=True,
            postgresql_where=sa.text("redemption_id IS NOT NULL"),
        ),
        # The balance query: SUM(delta) for one member in one campaign.
        sa.Index("ix_points_ledger_member_id_campaign_id", "member_id", "campaign_id"),
    )


# --------------------------------------------------------------------------- consent


class Consent(Base):
    """PDPA consent record. Active = granted and not withdrawn."""

    __tablename__ = "consent"

    id: Mapped[uuid.UUID] = _pk()
    member_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("member.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    # Which wording the member agreed to — needed to prove what was consented to.
    version: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.CheckConstraint("purpose IN ('health_data')", name="purpose_valid"),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= granted_at", name="withdrawn_after_granted"
        ),
        # At most one ACTIVE consent per member per purpose; withdrawn ones stay as history.
        sa.Index(
            "uq_consent_member_purpose_active",
            "member_id",
            "purpose",
            unique=True,
            postgresql_where=sa.text("withdrawn_at IS NULL"),
        ),
    )


# ---------------------------------------------------------------------- health data


class HealthRecord(Base):
    """Sensitive personal data (PDPA มาตรา 26). Separate table, consent-gated on write,
    role-gated + audited on admin read. Store only what before/after actually compares."""

    __tablename__ = "health_record"

    id: Mapped[uuid.UUID] = _pk()
    member_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("member.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("campaign.id", ondelete="RESTRICT"), nullable=False
    )
    phase: Mapped[str] = mapped_column(sa.String(8), nullable=False)
    measured_on: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # All measures optional: an unknown value stays NULL, it is never invented.
    weight_kg: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2))
    # Usually captured once, in the 'before' record. BMI is NOT stored: it is derived at
    # read time from weight + height, so it can never disagree with them.
    height_cm: Mapped[Decimal | None] = mapped_column(sa.Numeric(4, 1))
    resting_hr: Mapped[int | None] = mapped_column(sa.SmallInteger)
    systolic: Mapped[int | None] = mapped_column(sa.SmallInteger)
    diastolic: Mapped[int | None] = mapped_column(sa.SmallInteger)
    # The retention promise made when this record was stored: campaign.ends_on +
    # settings.health_retention_days, computed by the use case. Deliberately NOT a
    # server_default or a derived value — PDPA accountability means the commitment is
    # frozen onto the row, so later policy changes can't silently extend it.
    retention_until: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.CheckConstraint("phase IN ('before', 'after')", name="phase_valid"),
        sa.CheckConstraint(
            "weight_kg IS NULL OR (weight_kg > 0 AND weight_kg < 400)", name="weight_sane"
        ),
        sa.CheckConstraint(
            "height_cm IS NULL OR (height_cm BETWEEN 80 AND 250)", name="height_sane"
        ),
        sa.CheckConstraint(
            "resting_hr IS NULL OR (resting_hr BETWEEN 20 AND 250)", name="hr_sane"
        ),
        sa.CheckConstraint(
            "systolic IS NULL OR (systolic BETWEEN 50 AND 300)", name="systolic_sane"
        ),
        sa.CheckConstraint(
            "diastolic IS NULL OR (diastolic BETWEEN 30 AND 200)", name="diastolic_sane"
        ),
        # One before and one after per member per campaign — the write is an upsert.
        sa.UniqueConstraint(
            "member_id", "campaign_id", "phase", name="uq_health_record_member_campaign_phase"
        ),
        # Drives the purge job: WHERE retention_until < now().
        sa.Index("ix_health_record_retention_until", "retention_until"),
    )


# ------------------------------------------------------------------------- audit log


class AuditLog(Base):
    """Who touched whose sensitive data, and when. PDPA accountability.

    `detail` is for non-sensitive context only (ids, campaign) — never health values."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _pk()
    actor_member_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("member.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    subject_member_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("member.id", ondelete="SET NULL")
    )
    detail: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (
        sa.Index("ix_audit_log_subject_member_id_created_at", "subject_member_id", "created_at"),
    )
