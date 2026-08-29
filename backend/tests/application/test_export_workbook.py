"""The largest single disclosure the app can make, so these are mostly about limits.

Four things have to hold, and each of them is a way this feature could quietly become a
PDPA breach instead of a spreadsheet:

  - only the superuser can do it;
  - the sensitive sheets are off unless the flag says otherwise;
  - every member whose sensitive data leaves gets their own audit row, and nobody
    without live consent is in the file at all;
  - nothing measured ever reaches the audit log.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.ports.workbook_renderer import Sheet
from app.application.use_cases.export_workbook import ExportWorkbook
from app.domain.audit import AuditAction
from app.domain.campaign import Campaign, CampaignType
from app.domain.consent import Consent, ConsentPurpose
from app.domain.entities import (
    Member,
    MemberProfile,
    MemberRole,
    RunEntry,
    RunSource,
    Sex,
    ShirtSize,
)
from app.domain.errors import NotAuthorized
from app.domain.health import HealthPhase, HealthRecord
from app.domain.redemption import PointsEntry
from app.domain.screening import Screening
from tests.fakes.fake_export_uow import FakeExportUnitOfWork
from tests.fakes.fake_health_uow import FakeConsentRepository
from tests.fakes.fake_uow import FakeAuditRepository, FakePointsLedgerRepository, FixedClock
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeHealthRepository,
    FakeMemberRepository,
    FakeRunRepository,
    FakeScreeningRepository,
)

NOW = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
BOSS = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DAO = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
CONSENT_VERSION = "v2"
CAMPAIGN = Campaign.create(
    code="km100", name="100 กม.", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), config={"target_km": 100},
)


class RecordingRenderer:
    """Stands in for openpyxl. Keeps the sheets so a test can look at what would have
    been written — which is the only way to assert that a value did NOT go into a file."""

    def __init__(self) -> None:
        self.sheets: list[Sheet] = []

    def render(self, sheets: Sequence[Sheet]) -> bytes:
        self.sheets = list(sheets)
        return b"xlsx-bytes"

    def sheet(self, key: str) -> Sheet:
        return next(s for s in self.sheets if s.key == key)

    @property
    def keys(self) -> list[str]:
        return [s.key for s in self.sheets]


def member(
    member_id: UUID, role: MemberRole = MemberRole.MEMBER, name: str = "นักวิ่ง"
) -> Member:
    return Member(
        id=member_id, clerk_user_id=f"clerk_{member_id}", display_name=name, role=role,
        created_at=NOW,
        profile=MemberProfile(
            full_name_th=name, birth_date=date(1990, 5, 4), sex=Sex.FEMALE,
            position="พยาบาล", department="อายุรกรรม", shirt_size=ShirtSize.M,
            phone="0800000000", emergency_contact_name="ญาติ",
            emergency_contact_phone="0811111111",
        ),
    )


def consent_for(member_id: UUID, withdrawn: bool = False) -> Consent:
    return Consent(
        id=UUID(int=int(member_id) % (2**128 - 1)),
        member_id=member_id,
        purpose=ConsentPurpose.HEALTH_DATA,
        version=CONSENT_VERSION,
        granted_at=NOW,
        withdrawn_at=NOW if withdrawn else None,
    )


def health_for(member_id: UUID) -> HealthRecord:
    return HealthRecord(
        id=UUID(int=7), member_id=member_id, campaign_id=CAMPAIGN.id,
        phase=HealthPhase.BEFORE, measured_on=date(2026, 8, 1),
        weight_kg=Decimal("72.50"), height_cm=Decimal("165.0"), resting_hr=68,
        systolic=118, diastolic=76, retention_until=NOW, created_at=NOW,
    )


def screening_for(member_id: UUID) -> Screening:
    return Screening(
        id=UUID(int=8), member_id=member_id, version="v2",
        answers={"heart_condition": True, "chest_pain": False, "dizziness": False},
        risk_acknowledged=True, screened_on=date(2026, 8, 1),
        created_at=NOW, updated_at=NOW,
    )


def run_for(member_id: UUID) -> RunEntry:
    return RunEntry.create(
        member_id=member_id, distance_km=Decimal("5.25"), duration_seconds=1800,
        run_date=date(2026, 8, 20), evidence_key="runs/x/y.jpeg",
        evidence_sha256="a" * 64, source=RunSource.APP_SCREENSHOT, now=NOW,
    )


def build(
    *,
    members: list[Member],
    health_enabled: bool = False,
    consents: list[Consent] | None = None,
    health: list[HealthRecord] | None = None,
    screenings: list[Screening] | None = None,
    runs: list[RunEntry] | None = None,
    ledger: list[PointsEntry] | None = None,
) -> tuple[ExportWorkbook, FakeExportUnitOfWork, RecordingRenderer]:
    uow = FakeExportUnitOfWork(
        members=FakeMemberRepository(members),
        campaigns=FakeCampaignRepository([CAMPAIGN]),
        runs=FakeRunRepository(runs or []),
        ledger=FakePointsLedgerRepository(ledger or []),
        screenings=FakeScreeningRepository(screenings or []),
        health=FakeHealthRepository(health or []),
        consents=FakeConsentRepository(consents or []),
        audit=FakeAuditRepository(),
        clock=FixedClock(NOW),
    )
    renderer = RecordingRenderer()
    use_case = ExportWorkbook(
        uow=uow,
        renderer=renderer,
        consent_version=CONSENT_VERSION,
        health_export_enabled=health_enabled,
    )
    return use_case, uow, renderer


class TestWhoMayExport:
    def test_the_superuser_may(self) -> None:
        use_case, _, _ = build(members=[member(BOSS, MemberRole.SUPERUSER)])

        result = use_case.execute(BOSS)

        assert result.content == b"xlsx-bytes"
        assert result.filename.endswith(".xlsx")

    def test_an_admin_may_not(self) -> None:
        """Reading one named member's data is an act an admin answers for. Taking
        everyone's at once is a different act, and it belongs to the person who answers
        for the club's data."""
        use_case, uow, renderer = build(members=[member(ALICE, MemberRole.ADMIN)])

        with pytest.raises(NotAuthorized):
            use_case.execute(ALICE)

        assert renderer.sheets == []
        assert uow.audit.committed_entries() == []

    def test_an_ordinary_member_may_not(self) -> None:
        use_case, uow, _ = build(members=[member(ALICE)])

        with pytest.raises(NotAuthorized):
            use_case.execute(ALICE)

        assert uow.audit.committed_entries() == []


class TestTheOperationalSheets:
    def test_they_are_always_present(self) -> None:
        use_case, _, renderer = build(members=[member(BOSS, MemberRole.SUPERUSER)])

        use_case.execute(BOSS)

        assert renderer.keys == [
            "members", "runs", "redemptions", "ledger", "rewards", "campaigns"
        ]

    def test_the_members_sheet_carries_no_sensitive_field(self) -> None:
        """Sex, birth date and the emergency contact are the มาตรา 26 half of the
        profile. They belong on the audited sheet, so that opening this tab is not the
        same act as opening that one."""
        use_case, _, renderer = build(members=[member(BOSS, MemberRole.SUPERUSER)])

        use_case.execute(BOSS)
        sheet = renderer.sheet("members")
        cells = [str(cell) for row in sheet.rows for cell in row]

        assert "1990-05-04" not in cells
        assert "หญิง" not in cells
        assert "ญาติ" not in cells
        assert "0811111111" not in cells
        # What it does carry: the ordinary half.
        assert "อายุรกรรม" in cells
        assert "M" in cells

    def test_points_and_distance_stay_decimal(self) -> None:
        """Golden rule #6 does not stop applying because the destination is Excel."""
        run = run_for(BOSS)
        entry = PointsEntry.for_run(
            member_id=BOSS, campaign_id=CAMPAIGN.id, points=Decimal("10.50"),
            run_entry_id=run.id, now=NOW,
        )
        use_case, _, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER)], runs=[run], ledger=[entry]
        )

        use_case.execute(BOSS)

        points = renderer.sheet("ledger").rows[0][2]
        distance = renderer.sheet("runs").rows[0][2]
        assert isinstance(points, Decimal)
        assert isinstance(distance, Decimal)
        assert str(points) == "10.50"

    def test_a_run_carries_its_pace_and_status(self) -> None:
        use_case, _, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER)], runs=[run_for(BOSS)]
        )

        use_case.execute(BOSS)
        row = renderer.sheet("runs").rows[0]

        assert row[4] == Decimal("5.714")  # 5.25 km in 30 min
        assert row[6] == "ผ่าน"


class TestTheFlag:
    def test_off_by_default_the_sensitive_sheets_are_absent(self) -> None:
        use_case, uow, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER)],
            consents=[consent_for(BOSS)],
            health=[health_for(BOSS)],
            screenings=[screening_for(BOSS)],
        )

        use_case.execute(BOSS)

        assert "health" not in renderer.keys
        assert "screening" not in renderer.keys
        assert "contact" not in renderer.keys
        # And nothing was read, so nothing is claimed to have been.
        assert [e.action for e in uow.audit.committed_entries()] == [AuditAction.EXPORT_WORKBOOK]

    def test_on_the_sensitive_sheets_appear(self) -> None:
        use_case, _, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER)],
            health_enabled=True,
            consents=[consent_for(BOSS)],
            health=[health_for(BOSS)],
            screenings=[screening_for(BOSS)],
        )

        use_case.execute(BOSS)

        assert renderer.sheet("health").rows
        assert renderer.sheet("screening").rows
        assert renderer.sheet("contact").rows

    def test_the_export_row_says_which_way_the_flag_was_set(self) -> None:
        use_case, uow, _ = build(members=[member(BOSS, MemberRole.SUPERUSER)])

        use_case.execute(BOSS)
        entry = next(
            e for e in uow.audit.committed_entries() if e.action is AuditAction.EXPORT_WORKBOOK
        )

        assert entry.detail["health_included"] is False


class TestConsentGatesTheSensitiveSheets:
    def test_a_member_without_consent_is_not_in_the_file(self) -> None:
        use_case, uow, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER, "หัวหน้า"), member(DAO, name="ดาว")],
            health_enabled=True,
            consents=[consent_for(BOSS)],  # Dao never consented
            health=[health_for(BOSS), health_for(DAO)],
        )

        use_case.execute(BOSS)
        names = [row[0] for row in renderer.sheet("health").rows]

        assert names == ["หัวหน้า"]
        assert not any(e.subject_member_id == DAO for e in uow.audit.committed_entries())

    def test_withdrawn_consent_closes_the_door_too(self) -> None:
        """Withdrawal stops processing without deleting anything. An export is
        processing."""
        use_case, _, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER)],
            health_enabled=True,
            consents=[consent_for(BOSS, withdrawn=True)],
            health=[health_for(BOSS)],
        )

        use_case.execute(BOSS)

        assert renderer.sheet("health").rows == []
        assert renderer.sheet("contact").rows == []


class TestEveryReadIsAccountedFor:
    def test_each_member_read_gets_their_own_audit_row(self) -> None:
        """The invariant in models.py: the sensitive fields cannot be reached without an
        audit row naming the member. An export is not an exception to it."""
        use_case, uow, _ = build(
            members=[member(BOSS, MemberRole.SUPERUSER), member(DAO)],
            health_enabled=True,
            consents=[consent_for(BOSS), consent_for(DAO)],
            health=[health_for(BOSS), health_for(DAO)],
            screenings=[screening_for(BOSS), screening_for(DAO)],
        )

        use_case.execute(BOSS)
        entries = uow.audit.committed_entries()
        by_action = {
            action: {e.subject_member_id for e in entries if e.action is action}
            for action in (
                AuditAction.VIEW_HEALTH, AuditAction.VIEW_SCREENING, AuditAction.VIEW_CONTACT
            )
        }

        assert by_action[AuditAction.VIEW_HEALTH] == {BOSS, DAO}
        assert by_action[AuditAction.VIEW_SCREENING] == {BOSS, DAO}
        assert by_action[AuditAction.VIEW_CONTACT] == {BOSS, DAO}

    def test_the_export_itself_is_recorded_with_sheet_names_and_counts(self) -> None:
        use_case, uow, _ = build(
            members=[member(BOSS, MemberRole.SUPERUSER)], runs=[run_for(BOSS)]
        )

        use_case.execute(BOSS)
        entry = next(
            e for e in uow.audit.committed_entries() if e.action is AuditAction.EXPORT_WORKBOOK
        )

        assert entry.actor_member_id == BOSS
        # No subject: this one is about all of them at once.
        assert entry.subject_member_id is None
        assert entry.detail["members"] == 1
        assert entry.detail["runs"] == 1

    def test_the_audit_rows_and_the_file_commit_together(self) -> None:
        use_case, uow, _ = build(members=[member(BOSS, MemberRole.SUPERUSER)])

        use_case.execute(BOSS)

        assert uow.committed
        assert not uow.rolled_back

    def test_a_failed_render_leaves_no_audit_row_claiming_a_file(self) -> None:
        """The other half of the same guarantee: no row saying an export happened when
        nothing was handed over."""

        class BrokenRenderer:
            def render(self, sheets: Sequence[Sheet]) -> bytes:
                raise RuntimeError("disk full")

        _, uow, _ = build(members=[member(BOSS, MemberRole.SUPERUSER)])
        use_case = ExportWorkbook(
            uow=uow,
            renderer=BrokenRenderer(),
            consent_version=CONSENT_VERSION,
            health_export_enabled=False,
        )

        with pytest.raises(RuntimeError):
            use_case.execute(BOSS)

        assert uow.audit.committed_entries() == []
        assert uow.rolled_back


class TestNothingMeasuredReachesTheLog:
    def test_no_health_value_appears_in_any_audit_detail(self) -> None:
        """Golden rule #8. The values are in the file, which is the point; they must not
        also be in the log, which travels and persists differently."""
        use_case, uow, _ = build(
            members=[member(BOSS, MemberRole.SUPERUSER)],
            health_enabled=True,
            consents=[consent_for(BOSS)],
            health=[health_for(BOSS)],
            screenings=[screening_for(BOSS)],
        )

        use_case.execute(BOSS)
        rendered = " ".join(
            f"{k}={v}" for e in uow.audit.committed_entries() for k, v in e.detail.items()
        )

        for forbidden in ("72.5", "165", "68", "118", "76", "0811111111", "1990-05-04"):
            assert forbidden not in rendered

    def test_the_screening_sheet_carries_a_count_not_the_answers(self) -> None:
        """Which condition somebody declared is health data about a named person. The
        count is what tells an organiser to look; the detail stays behind the app, where
        reading it is its own audited act."""
        use_case, _, renderer = build(
            members=[member(BOSS, MemberRole.SUPERUSER)],
            health_enabled=True,
            consents=[consent_for(BOSS)],
            screenings=[screening_for(BOSS)],
        )

        use_case.execute(BOSS)
        row = renderer.sheet("screening").rows[0]

        assert row[3] == 1  # one 'yes' among three questions
        assert "heart_condition" not in [str(cell) for cell in row]
