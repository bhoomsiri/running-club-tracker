"""club announcements

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-16

News the club puts out: what is happening, when the next group run is, who won what.

This is the only table in the schema whose rows are served to callers with no token —
the landing page has to say something to someone who has not signed up yet. Nothing
personal belongs in `body`, which is a rule for whoever is typing rather than one the
schema can enforce, so the admin form says it too.

`is_published` is how a notice is taken down: hidden rather than deleted, so the person
who wrote it can still find it when somebody asks about it a month later.

The partial index matches the public query exactly (published, newest first) and is the
only one this table needs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "announcement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "is_published", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
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
    )
    op.create_index(
        "ix_announcement_published_created_at",
        "announcement",
        ["created_at"],
        postgresql_where=sa.text("is_published"),
    )


def downgrade() -> None:
    op.drop_index("ix_announcement_published_created_at", table_name="announcement")
    op.drop_table("announcement")
