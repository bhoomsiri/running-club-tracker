"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-14

Hand-written (there is no live DB to autogenerate from yet). It must stay in step
with app/adapters/persistence/models.py.

Note on CHECK names: they are written SHORT here ("role_valid", not
"ck_member_role_valid") on purpose. Alembic applies the metadata naming convention
`ck_%(table_name)s_%(constraint_name)s` to whatever name is given, so a full name would
land in the database as `ck_member_ck_member_role_valid`. The short form expands to
exactly `ck_member_role_valid`, which is what models.py declares and what the database
actually contains — verify with:

    SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_%';
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="member", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('member', 'admin', 'superuser')", name="role_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_member"),
        sa.UniqueConstraint("clerk_user_id", name="uq_member_clerk_user_id"),
    )
    # At most one superuser account.
    op.create_index(
        "uq_member_single_superuser",
        "member",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'superuser'"),
    )

    op.create_table(
        "campaign",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "type IN ('cumulative_distance', 'redeem_reward', 'daily_threshold_reward')",
            name="type_valid",
        ),
        sa.CheckConstraint("ends_on >= starts_on", name="window_ordered"),
        sa.PrimaryKeyConstraint("id", name="pk_campaign"),
        sa.UniqueConstraint("code", name="uq_campaign_code"),
    )

    op.create_table(
        "consent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IN ('health_data')", name="purpose_valid"),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= granted_at",
            name="withdrawn_after_granted",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["member.id"], name="fk_consent_member_id_member", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_consent"),
    )
    # At most one ACTIVE consent per member per purpose.
    op.create_index(
        "uq_consent_member_purpose_active",
        "consent",
        ["member_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("withdrawn_at IS NULL"),
    )

    op.create_table(
        "run_entry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("distance_km", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("evidence_key", sa.String(length=255), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("review_status", sa.String(length=16), server_default="ok", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "distance_km > 0 AND distance_km <= 200", name="distance_sane"
        ),
        sa.CheckConstraint(
            "duration_seconds > 0 AND duration_seconds <= 86400",
            name="duration_sane",
        ),
        sa.CheckConstraint(
            "source IN ('app_screenshot', 'manual_photo')", name="source_valid"
        ),
        sa.CheckConstraint(
            "review_status IN ('ok', 'flagged', 'rejected')",
            name="review_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["member.id"], name="fk_run_entry_member_id_member", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_entry"),
        sa.UniqueConstraint(
            "member_id", "evidence_sha256", name="uq_run_entry_member_evidence"
        ),
    )
    op.create_index("ix_run_entry_evidence_sha256", "run_entry", ["evidence_sha256"])
    op.create_index("ix_run_entry_member_id_run_date", "run_entry", ["member_id", "run_date"])

    op.create_table(
        "health_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("phase", sa.String(length=8), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        # BMI is derived from weight + height at read time, never stored.
        sa.Column("height_cm", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("resting_hr", sa.SmallInteger(), nullable=True),
        sa.Column("systolic", sa.SmallInteger(), nullable=True),
        sa.Column("diastolic", sa.SmallInteger(), nullable=True),
        # Set by the use case (campaign.ends_on + HEALTH_RETENTION_DAYS), never a
        # server_default: the retention promise is frozen onto the row.
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("phase IN ('before', 'after')", name="phase_valid"),
        sa.CheckConstraint(
            "weight_kg IS NULL OR (weight_kg > 0 AND weight_kg < 400)",
            name="weight_sane",
        ),
        sa.CheckConstraint(
            "height_cm IS NULL OR (height_cm BETWEEN 80 AND 250)",
            name="height_sane",
        ),
        sa.CheckConstraint(
            "resting_hr IS NULL OR (resting_hr BETWEEN 20 AND 250)",
            name="hr_sane",
        ),
        sa.CheckConstraint(
            "systolic IS NULL OR (systolic BETWEEN 50 AND 300)",
            name="systolic_sane",
        ),
        sa.CheckConstraint(
            "diastolic IS NULL OR (diastolic BETWEEN 30 AND 200)",
            name="diastolic_sane",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaign.id"],
            name="fk_health_record_campaign_id_campaign",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["member.id"],
            name="fk_health_record_member_id_member",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_health_record"),
        sa.UniqueConstraint(
            "member_id",
            "campaign_id",
            "phase",
            name="uq_health_record_member_campaign_phase",
        ),
    )
    # Drives the purge job: WHERE retention_until < now().
    op.create_index("ix_health_record_retention_until", "health_record", ["retention_until"])

    op.create_table(
        "reward",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("points_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("points_cost > 0", name="cost_positive"),
        sa.CheckConstraint("stock >= 0", name="stock_non_negative"),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaign.id"],
            name="fk_reward_campaign_id_campaign",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reward"),
    )
    op.create_index("ix_reward_campaign_id", "reward", ["campaign_id"])

    op.create_table(
        "redemption",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("reward_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("points_spent", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("points_spent > 0", name="spent_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'fulfilled', 'cancelled')", name="status_valid"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaign.id"],
            name="fk_redemption_campaign_id_campaign",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["member.id"], name="fk_redemption_member_id_member", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reward_id"], ["reward.id"], name="fk_redemption_reward_id_reward", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_redemption"),
    )
    op.create_index("ix_redemption_member_id", "redemption", ["member_id"])

    # After redemption: points_ledger references both run_entry and redemption.
    op.create_table(
        "points_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("delta", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("run_entry_id", sa.Uuid(), nullable=True),
        sa.Column("redemption_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "reason IN ('run_earned', 'redeemed', 'adjustment', 'reversal')",
            name="reason_valid",
        ),
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
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaign.id"],
            name="fk_points_ledger_campaign_id_campaign",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["member.id"],
            name="fk_points_ledger_member_id_member",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["redemption_id"],
            ["redemption.id"],
            name="fk_points_ledger_redemption_id_redemption",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_entry_id"],
            ["run_entry.id"],
            name="fk_points_ledger_run_entry_id_run_entry",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_points_ledger"),
    )
    # Idempotency: one credit per (campaign, run, reason) and one charge per
    # (redemption, reason) — a later reversal is still allowed.
    op.create_index(
        "uq_points_ledger_campaign_run_reason",
        "points_ledger",
        ["campaign_id", "run_entry_id", "reason"],
        unique=True,
        postgresql_where=sa.text("run_entry_id IS NOT NULL"),
    )
    op.create_index(
        "uq_points_ledger_redemption_reason",
        "points_ledger",
        ["redemption_id", "reason"],
        unique=True,
        postgresql_where=sa.text("redemption_id IS NOT NULL"),
    )
    op.create_index(
        "ix_points_ledger_member_id_campaign_id", "points_ledger", ["member_id", "campaign_id"]
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_member_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("subject_member_id", sa.Uuid(), nullable=True),
        sa.Column(
            "detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_member_id"],
            ["member.id"],
            name="fk_audit_log_actor_member_id_member",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_member_id"],
            ["member.id"],
            name="fk_audit_log_subject_member_id_member",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index(
        "ix_audit_log_subject_member_id_created_at",
        "audit_log",
        ["subject_member_id", "created_at"],
    )


def downgrade() -> None:
    # Reverse of the creation order: points_ledger holds FKs into redemption/run_entry.
    op.drop_table("audit_log")
    op.drop_table("points_ledger")
    op.drop_table("redemption")
    op.drop_table("reward")
    op.drop_table("health_record")
    op.drop_table("run_entry")
    op.drop_table("consent")
    op.drop_table("campaign")
    op.drop_table("member")
