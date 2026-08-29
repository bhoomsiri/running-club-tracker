"""the picture Clerk already holds for each member

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-29

The club has no photo upload and is not getting one. Almost everybody signs in with
Google or LINE, which hands Clerk a picture already, so the cheapest way to put faces on
the dashboard and the leaderboard is to keep the one that is there.

Written only by the verified `user.created` / `user.updated` webhook, like `display_name`
and `role` — identity comes from Clerk, never from something a client sends.

`has_image` is Clerk's own flag and the reason this is two columns rather than one:
every account has an `image_url`, and for someone who never set a picture it points at a
generated default. Storing the URL without the flag would mean the app could not tell
"this is their photo" from "this is a stranger's styling", and would show the second as
though the member had chosen it. False means fall back to the club's initials avatar.

Nullable and defaulted, so existing rows are simply "no picture known yet" until their
next `user.updated` — no backfill, and nothing to backfill from without calling Clerk.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("member", sa.Column("image_url", sa.String(512), nullable=True))
    op.add_column(
        "member",
        sa.Column(
            "has_image", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("member", "has_image")
    op.drop_column("member", "image_url")
