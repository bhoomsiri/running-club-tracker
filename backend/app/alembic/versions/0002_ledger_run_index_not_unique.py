"""points_ledger: the (campaign, run, reason) index is no longer unique

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-15

The unique index was written when points were credited once per run. Earning is now a
reconciliation, and a single run can legitimately be the attribution point for more than
one row of the same reason over its life:

    submit  -> run_earned  (+1)
    reject  -> reversal    (-1)
    approve -> run_earned  (+1)   <-- refused by the unique index, as a 500

Idempotency no longer depends on this index: `reconcile_campaign_points` computes
`target - credited` and writes nothing when that is zero, under the per-account advisory
lock that serialises concurrent writers. The index stays as a plain one, because the
lookup it supports is still useful.

The redemption-side unique index is untouched: a redemption really can only be charged
or refunded once, and nothing recomputes it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WHERE_RUN = sa.text("run_entry_id IS NOT NULL")


def upgrade() -> None:
    op.drop_index("uq_points_ledger_campaign_run_reason", table_name="points_ledger")
    op.create_index(
        "ix_points_ledger_campaign_run_reason",
        "points_ledger",
        ["campaign_id", "run_entry_id", "reason"],
        postgresql_where=WHERE_RUN,
    )


def downgrade() -> None:
    op.drop_index("ix_points_ledger_campaign_run_reason", table_name="points_ledger")
    op.create_index(
        "uq_points_ledger_campaign_run_reason",
        "points_ledger",
        ["campaign_id", "run_entry_id", "reason"],
        unique=True,
        postgresql_where=WHERE_RUN,
    )
