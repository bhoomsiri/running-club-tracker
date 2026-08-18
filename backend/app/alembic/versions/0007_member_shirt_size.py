"""which finisher shirt to order for a member

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-18

Everyone who joins gets a finisher shirt, so the size has to be collected once, up front,
from the member themselves — chasing a hundred people for it afterwards is how a shirt
order slips a month.

A short string rather than an enum type in the database: the set of sizes is fixed in the
domain (`ShirtSize`), and a Postgres enum would make adding "6XL" a migration with a lock
on it instead of a one-line change.

Nullable, like the profile columns beside it — rows already exist for members who joined
before it was asked for. `is_complete` is what insists on it, so every existing member is
sent back through the profile step once. That is the intended effect: without it the club
has no size for the people who signed up first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("member", sa.Column("shirt_size", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("member", "shirt_size")
