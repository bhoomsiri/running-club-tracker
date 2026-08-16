"""a catalogue photo for a reward

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16

A reward is easier to want when you can see it. This holds the object key in the private
bucket's `rewards/` namespace — never a URL: the link members are shown is presigned per
request and expires in minutes, so a stored one would be broken within the hour and a
public one would defeat the private bucket.

Nullable because a reward is perfectly usable without a picture, and the rewards already
in the catalogue have none.

Dropping the column on downgrade forgets which object belonged to which reward; the
objects themselves stay in the bucket, orphaned rather than deleted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("reward", sa.Column("image_key", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("reward", "image_key")
