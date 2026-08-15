"""member profile fields, and the screening table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

Two things the club needs before it can run an activity responsibly:

  - who a member actually is, and who to call if they collapse on a run. The columns are
    nullable because a member row exists from their first authenticated request, long
    before any of this is asked for; the onboarding gate is what insists on them, not
    the schema.
  - a PAR-Q+ pre-exercise screening. One row per member (member_id is unique), replaced
    when they answer again — this records what is true now, and keeping every past draft
    of someone's cardiac history would be a liability rather than an asset.

`sex`, the emergency contact, and every screening answer are sensitive personal data
under PDPA มาตรา 26, in the same class as health_record: consent-gated, and readable by
an admin only through an audited path.

Downgrade drops the screening table and the six columns, which destroys those answers.
That is the correct behaviour for a schema rollback and the reason not to run one
against production without a backup.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_PROFILE_COLUMNS = (
    ("full_name_th", sa.String(200)),
    ("birth_year", sa.SmallInteger()),
    ("sex", sa.String(6)),
    ("phone", sa.String(16)),
    ("emergency_contact_name", sa.String(200)),
    ("emergency_contact_phone", sa.String(16)),
)


def upgrade() -> None:
    for name, type_ in _PROFILE_COLUMNS:
        op.add_column("member", sa.Column(name, type_, nullable=True))

    # Short names on purpose: Alembic expands them through the naming convention, so a
    # fully-qualified name here would come out as ck_member_ck_member_sex_valid.
    op.create_check_constraint(
        "sex_valid", "member", "sex IS NULL OR sex IN ('male', 'female')"
    )
    op.create_check_constraint(
        "birth_year_range", "member", "birth_year IS NULL OR birth_year BETWEEN 1900 AND 2200"
    )

    op.create_table(
        "screening",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "member_id",
            sa.Uuid(),
            sa.ForeignKey("member.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("answers", JSONB(), nullable=False),
        sa.Column("risk_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("screened_on", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Shape only. That all eleven questions are answered is enforced in the domain:
        # a CHECK cannot contain the subquery that counting JSONB keys would require.
        sa.CheckConstraint("jsonb_typeof(answers) = 'object'", name="answers_is_object"),
    )


def downgrade() -> None:
    op.drop_table("screening")
    # Short names here too: the naming convention expands them on the way out exactly as
    # it did on the way in. Passing the expanded name produces
    # ck_member_ck_member_sex_valid, which matches nothing.
    op.drop_constraint("birth_year_range", "member", type_="check")
    op.drop_constraint("sex_valid", "member", type_="check")
    for name, _ in reversed(_PROFILE_COLUMNS):
        op.drop_column("member", name)
