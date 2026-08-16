"""the member's job and unit at the hospital

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

Every member of this club is hospital staff, so "who is this?" is really "which unit are
they in?" — that is how the club recognises people, and how it will report participation
back to the departments that sponsor it.

Free text, not a foreign key to a department table: a fixed list would be out of date
within a year, and the club is not the system of record for the hospital's org chart.

Nullable, like the profile columns beside them: rows already exist for members who joined
before these were asked for. The onboarding gate is what insists on them, not the schema
— and because `is_complete` now requires both, every existing member is sent back through
that step once, which is the intended effect rather than a side effect.

Unlike `sex` and the emergency contact these are ordinary personal data under PDPA, not
มาตรา 26 sensitive data, so they may be shown in an admin list without an audit row.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_COLUMNS = ("position", "department")


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column("member", sa.Column(name, sa.String(160), nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("member", name)
