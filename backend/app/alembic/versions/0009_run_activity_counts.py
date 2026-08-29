"""calories and steps, as the running app reported them

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-29

Two numbers most running apps already show beside the distance. Collecting them lets the
member's own dashboard say something about a run beyond how far it was, and they cost
nothing to carry: they arrive in the same screenshot the distance does.

Nullable, and that is the point rather than a concession. Most screenshots do not show
them, no member is made to type them, and every row that already exists predates the
question — so NULL means "not recorded", which is true, where 0 would mean "burned
nothing", which is not. No backfill: there is nothing to backfill them from.

Plain integers, not numeric. The Decimal rule is about money-like values — distance and
points, where a rounding error changes what someone is owed. Nothing is earned or
redeemed on the strength of a step count.

The CHECKs are deliberately wide: an ultramarathon is nowhere near 10,000 kcal or
200,000 steps, so they catch a misread digit or a units mix-up without refereeing
anyone's training. Same numbers as MAX_CALORIES_BURNED / MAX_STEPS in the domain, so a
value the domain accepts is never rejected here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("run_entry", sa.Column("calories_burned", sa.Integer(), nullable=True))
    op.add_column("run_entry", sa.Column("steps", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "calories_sane",
        "run_entry",
        "calories_burned IS NULL OR (calories_burned > 0 AND calories_burned < 10000)",
    )
    op.create_check_constraint(
        "steps_sane", "run_entry", "steps IS NULL OR (steps > 0 AND steps < 200000)"
    )


def downgrade() -> None:
    # The SHORT names, not the ck_run_entry_… ones the database holds: the metadata's
    # naming convention expands them, and passing the expanded name gets it expanded a
    # second time into ck_run_entry_ck_run_entry_steps_sane. `alembic downgrade base` is
    # a CI step, so the mistake fails the build rather than surfacing during a rollback.
    op.drop_constraint("steps_sane", "run_entry", type_="check")
    op.drop_constraint("calories_sane", "run_entry", type_="check")
    op.drop_column("run_entry", "steps")
    op.drop_column("run_entry", "calories_burned")
