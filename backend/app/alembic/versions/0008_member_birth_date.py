"""the member's whole birth date, not just the year

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-18

A year cannot say whether somebody has had their birthday yet, and the club's minimum-age
rule is about a person on a day. It also asks members to do arithmetic — the year field
was the one people filled in as พ.ศ. — where a date picker asks them to point at a date.

A replace rather than a backfill: this is pre-launch, no real member has filled the
profile in, and converting "born in 1990" into a date would mean inventing a day. Golden
rule #4 — an unknown value is absent, never guessed. Any year already in the column is
dropped with it, which is why this migration must not be run again once real rows exist.

The CHECK is a floor only. "Not in the future" and "at least MIN_AGE_YEARS old" both
depend on the day the row is written, and a CHECK constraint may not call CURRENT_DATE;
those rules live in `build_profile`, the one path that writes this column.

Downgrade restores an empty birth_year column: the dates are gone, and there is nothing
honest to put back in it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Short name: the naming convention expands it on the way out exactly as it did on
    # the way in, so the fully-qualified name here would match nothing.
    op.drop_constraint("birth_year_range", "member", type_="check")
    op.drop_column("member", "birth_year")
    op.add_column("member", sa.Column("birth_date", sa.Date(), nullable=True))
    op.create_check_constraint(
        "birth_date_floor", "member", "birth_date IS NULL OR birth_date >= DATE '1900-01-01'"
    )


def downgrade() -> None:
    op.drop_constraint("birth_date_floor", "member", type_="check")
    op.drop_column("member", "birth_date")
    op.add_column("member", sa.Column("birth_year", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "birth_year_range", "member", "birth_year IS NULL OR birth_year BETWEEN 1900 AND 2200"
    )
