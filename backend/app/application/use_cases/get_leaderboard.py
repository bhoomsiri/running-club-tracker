"""The club standing, as members see each other.

Deliberately narrow: a name, a distance, a points balance, a number of runs. No unit, no
role, no id of anything else — this list goes to every member, so it carries the least
that still makes it a leaderboard. Compare with `GetClubOverview`, which answers a
different question for one person and still holds nothing sensitive; between them the
rule is the same, and this one is stricter because the audience is wider.

Signed-in members only, not public. Names and distances are ordinary personal data, but
publishing who at the hospital runs how far to anyone who finds the URL is not something
the club has asked anyone's permission for.

The caller's own row travels with the list. Someone in 60th place opening a top-ten and
finding themselves absent has learned nothing; "#37 จาก 94" is the number they came for.

Aggregated the same way the admin overview is — a handful of queries for the whole club
rather than a handful per member — and derived from the same runs through the same
policy, so the leaderboard and the dashboard cannot disagree about anyone's distance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.run_repository import RunRepository
from app.application.services.points_reconciliation import valid_runs_of
from app.domain.campaigns import policy_for
from app.domain.entities import Member, RunEntry
from app.domain.errors import MemberNotFound

KM = Decimal("0.001")


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    member_id: UUID
    name: str
    # None when the member never set a picture at Clerk — the screen draws its own
    # initials avatar rather than Clerk's generated default, which is somebody else's
    # styling on a member who chose nothing.
    image_url: str | None
    total_distance_km: Decimal
    points: Decimal | None
    run_count: int


@dataclass(frozen=True)
class Leaderboard:
    entries: list[LeaderboardEntry]
    # The caller's own line, always — even when they are far below the fold.
    me: LeaderboardEntry
    total_members: int
    # Which campaign the points column is counting, so the UI can label it rather than
    # guess. None when no active campaign awards any.
    points_campaign_name: str | None


class GetLeaderboard:
    def __init__(
        self,
        members: MemberRepository,
        runs: RunRepository,
        campaigns: CampaignRepository,
        ledger: PointsLedgerRepository,
    ) -> None:
        self._members = members
        self._runs = runs
        self._campaigns = campaigns
        self._ledger = ledger

    def execute(self, member_id: UUID) -> Leaderboard:
        caller = self._members.get(member_id)
        if caller is None:
            raise MemberNotFound(str(member_id))

        # One campaign's points, named. Summing balances across campaigns would add up
        # numbers that are not the same currency.
        points_campaign = next(
            (c for c in self._campaigns.list_active() if policy_for(c.type).tracks_points),
            None,
        )
        balances = (
            self._ledger.balances_for_campaign(points_campaign.id)
            if points_campaign is not None
            else {}
        )
        runs_by_member = _group_by_member(self._runs.list_all())

        ranked = _rank(
            [
                _row_for(member, runs_by_member.get(member.id, []), balances)
                for member in self._members.list_all()
            ]
        )

        me = next((entry for entry in ranked if entry.member_id == caller.id), None)
        if me is None:
            # A member whose row is missing from a list built over every member means
            # they were deleted mid-request; treat them as unranked rather than crash.
            me = LeaderboardEntry(
                rank=len(ranked) + 1,
                member_id=caller.id,
                name=caller.preferred_name,
                image_url=_avatar(caller),
                total_distance_km=Decimal("0").quantize(KM),
                points=None if points_campaign is None else Decimal("0"),
                run_count=0,
            )

        return Leaderboard(
            entries=ranked,
            me=me,
            total_members=len(ranked),
            points_campaign_name=None if points_campaign is None else points_campaign.name,
        )


def _avatar(member: Member) -> str | None:
    """Only a picture the member actually set. `has_image` false means Clerk's URL points
    at a generated default, and passing that on would show a stranger's styling as though
    it were their choice."""
    return member.image_url if member.has_image else None


def _row_for(
    member: Member, all_runs: list[RunEntry], balances: dict[UUID, Decimal]
) -> LeaderboardEntry:
    # Rejected runs count for nothing, exactly as on the member's own screen.
    counted = valid_runs_of(all_runs)
    return LeaderboardEntry(
        # Filled in by _rank once the whole field is sorted.
        rank=0,
        member_id=member.id,
        # The Thai full name once given, else what Clerk supplied.
        name=member.preferred_name,
        image_url=_avatar(member),
        total_distance_km=sum(
            (run.distance_km for run in counted), start=Decimal("0")
        ).quantize(KM),
        points=balances.get(member.id, Decimal("0")) if balances else None,
        run_count=len(counted),
    )


def _rank(rows: list[LeaderboardEntry]) -> list[LeaderboardEntry]:
    """Furthest first, with ties sharing a place.

    Standard competition ranking: two members on 40 km are both 2nd and the next is 4th.
    Breaking a genuine tie by name would invent a difference that does not exist, and the
    person put second would be right to complain.
    """
    ordered = sorted(rows, key=lambda row: (-row.total_distance_km, row.name))

    ranked: list[LeaderboardEntry] = []
    for index, row in enumerate(ordered):
        previous = ranked[-1] if ranked else None
        rank = (
            previous.rank
            if previous is not None and previous.total_distance_km == row.total_distance_km
            else index + 1
        )
        # Only the rank is decided here; everything else is carried over as it was, so a
        # field added to the entry does not have to be remembered in this loop too.
        ranked.append(replace(row, rank=rank))
    return ranked


def _group_by_member(runs: list[RunEntry]) -> dict[UUID, list[RunEntry]]:
    grouped: dict[UUID, list[RunEntry]] = {}
    for run in runs:
        grouped.setdefault(run.member_id, []).append(run)
    return grouped
