"""Bring a member's ledger into line with what the campaign's policy says they earned.

This replaces crediting points run-by-run, which cannot express a format where the
earning unit is a *day*: three 4 km runs qualify a day together, so no single run owns
the point, and rejecting one of them can cost the whole day even though that run never
carried a ledger row. Reversing "the row belonging to this run" would silently miss it.

Instead there is one operation, used everywhere points can change:

    target   = what the policy says the member has earned from their valid runs
    credited = what the ledger has already awarded for earning
    delta    = target - credited   ->  write one row, or none

Consequences worth knowing:
  - it is idempotent by construction: run it twice and the second call sees delta 0;
  - it works the same for linear formats (where it produces exactly what per-run
    crediting produced) and for threshold formats;
  - `adjustment` rows are excluded from `credited`, so a superuser's manual correction
    is not treated as earning and quietly reconciled away on the next run.

Callers must pass the runs that COUNT (rejected ones filtered out) — the policies never
see `review_status`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.domain.campaign import Campaign
from app.domain.campaigns import policy_for
from app.domain.entities import RunEntry
from app.domain.redemption import PointsEntry


def reconcile_campaign_points(
    *,
    ledger: PointsLedgerRepository,
    member_id: UUID,
    campaign: Campaign,
    valid_runs: Sequence[RunEntry],
    trigger_run_id: UUID,
    now: datetime,
) -> PointsEntry | None:
    """Write at most one ledger row so earnings match the policy. Returns it, or None.

    `trigger_run_id` is attribution only — the run whose submission or review caused
    this. It is what makes the row traceable back to a cause.
    """
    policy = policy_for(campaign.type)
    if not policy.tracks_points:
        return None

    # Rule #5: the account lock comes first, before the balance is read.
    ledger.serialize_account(member_id, campaign.id)

    target = policy.progress(campaign, valid_runs).value
    credited = ledger.credited_total(member_id, campaign.id)
    delta = target - credited

    if delta == 0:
        return None

    entry = (
        PointsEntry.for_run(
            member_id=member_id,
            campaign_id=campaign.id,
            points=delta,
            run_entry_id=trigger_run_id,
            now=now,
        )
        if delta > 0
        else PointsEntry.reversal(
            member_id=member_id,
            campaign_id=campaign.id,
            points=-delta,
            run_entry_id=trigger_run_id,
            now=now,
        )
    )
    ledger.add(entry)
    return entry


def reconcile_all_campaigns(
    *,
    ledger: PointsLedgerRepository,
    campaigns: Sequence[Campaign],
    member_id: UUID,
    valid_runs: Sequence[RunEntry],
    trigger_run_id: UUID,
    now: datetime,
) -> list[PointsEntry]:
    """One run can sit in several campaigns at once, so every active one is reconciled."""
    written = []
    for campaign in campaigns:
        entry = reconcile_campaign_points(
            ledger=ledger,
            member_id=member_id,
            campaign=campaign,
            valid_runs=valid_runs,
            trigger_run_id=trigger_run_id,
            now=now,
        )
        if entry is not None:
            written.append(entry)
    return written


def counts_toward_earning(run: RunEntry) -> bool:
    """A rejected run earns nothing and counts toward no progress. Flagged runs still
    count — they are awaiting a decision, not refused."""
    return not run.is_rejected


def valid_runs_of(runs: Sequence[RunEntry]) -> list[RunEntry]:
    return [run for run in runs if counts_toward_earning(run)]


__all__ = [
    "counts_toward_earning",
    "reconcile_all_campaigns",
    "reconcile_campaign_points",
    "valid_runs_of",
]
