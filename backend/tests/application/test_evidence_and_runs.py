"""Uploading evidence, submitting runs, and who may see which image."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.use_cases.extract_run_draft import ExtractRunDraft, ExtractRunDraftCommand
from app.application.use_cases.list_runs import ListMemberRuns, ListMyRuns
from app.application.use_cases.submit_run import SubmitRun, SubmitRunCommand
from app.application.use_cases.upload_evidence import UploadEvidence, UploadEvidenceCommand
from app.domain.campaign import Campaign, CampaignType
from app.domain.entities import Member, MemberRole, ReviewStatus, RunEntry, RunSource
from app.domain.errors import (
    DuplicateEvidence,
    InvalidImage,
    InvalidRunError,
    NotAuthorized,
)
from app.domain.evidence import ImageKind
from app.domain.redemption import LedgerReason
from tests.fakes.fake_storage import FakeImageStorage, FakeRunExtractor, PassthroughSanitizer
from tests.fakes.fake_uow import (
    FakePointsLedgerRepository,
    FakeRunSubmissionUnitOfWork,
    FixedClock,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeMemberRepository,
    FakeRunRepository,
)

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DAO = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
ADMIN = UUID("11111111-1111-1111-1111-111111111111")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 300
PNG = b"\x89PNG\r\n\x1a\n" + b"\x11" * 300


def member(member_id: UUID, role: MemberRole = MemberRole.MEMBER) -> Member:
    return Member(
        id=member_id, clerk_user_id=f"clerk_{member_id}", display_name="X",
        role=role, created_at=NOW,
    )


def key_for(member_id: UUID, data: bytes = JPEG, kind: str = "jpeg") -> str:
    digest = hashlib.sha256(b"scrubbed:" + data).hexdigest()
    return f"runs/{member_id}/{digest}.{kind}"


def run_for(member_id: UUID, key: str) -> RunEntry:
    return RunEntry.create(
        member_id=member_id, distance_km=Decimal("5"), duration_seconds=1800,
        run_date=date(2026, 6, 1), evidence_key=key,
        evidence_sha256=key.rsplit("/", 1)[1].rsplit(".", 1)[0],
        source=RunSource.APP_SCREENSHOT, now=NOW,
    )


class TestUploadEvidence:
    def test_the_image_is_scrubbed_before_it_is_stored(self) -> None:
        storage, sanitizer = FakeImageStorage(), PassthroughSanitizer()

        stored = UploadEvidence(storage, sanitizer).execute(
            UploadEvidenceCommand(member_id=ALICE, data=JPEG)
        )

        assert sanitizer.calls == ["jpeg"]
        # What lands in the bucket is the scrubbed version, never the original.
        assert storage.objects[stored.image_key][0].startswith(b"scrubbed:")

    def test_the_key_is_derived_from_the_member_and_the_scrubbed_content(self) -> None:
        stored = UploadEvidence(FakeImageStorage(), PassthroughSanitizer()).execute(
            UploadEvidenceCommand(member_id=ALICE, data=JPEG)
        )

        assert stored.image_key == key_for(ALICE)
        assert stored.sha256 == hashlib.sha256(b"scrubbed:" + JPEG).hexdigest()

    def test_the_stored_content_type_matches_the_real_format(self) -> None:
        storage = FakeImageStorage()

        stored = UploadEvidence(storage, PassthroughSanitizer()).execute(
            UploadEvidenceCommand(member_id=ALICE, data=PNG)
        )

        assert stored.kind is ImageKind.PNG
        assert storage.objects[stored.image_key][1] == "image/png"

    def test_a_file_that_is_not_an_image_never_reaches_storage(self) -> None:
        storage, sanitizer = FakeImageStorage(), PassthroughSanitizer()

        with pytest.raises(InvalidImage):
            UploadEvidence(storage, sanitizer).execute(
                UploadEvidenceCommand(member_id=ALICE, data=b"<?php ?>" + b" " * 300)
            )

        assert storage.objects == {}
        assert sanitizer.calls == []  # rejected before anything touches the file

    def test_the_same_image_from_the_same_member_lands_on_the_same_key(self) -> None:
        use_case = UploadEvidence(FakeImageStorage(), PassthroughSanitizer())

        first = use_case.execute(UploadEvidenceCommand(member_id=ALICE, data=JPEG))
        second = use_case.execute(UploadEvidenceCommand(member_id=ALICE, data=JPEG))

        assert first.image_key == second.image_key


REWARDS_CAMPAIGN = Campaign.create(
    code="rewards", name="Run for rewards", type=CampaignType.REDEEM_REWARD,
    starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), config={"points_per_km": 2},
)
DISTANCE_CAMPAIGN = Campaign.create(
    code="100km", name="100 km", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), config={"target_km": 100},
)


def submission_uow(
    runs: FakeRunRepository | None = None, campaigns: list[Campaign] | None = None
) -> FakeRunSubmissionUnitOfWork:
    return FakeRunSubmissionUnitOfWork(
        runs=runs or FakeRunRepository(),
        # A run must fall inside some active campaign's window. The distance campaign
        # earns no points, which keeps these tests about submission, not about earning.
        campaigns=FakeCampaignRepository(
            campaigns if campaigns is not None else [DISTANCE_CAMPAIGN]
        ),
        ledger=FakePointsLedgerRepository(),
        clock=FixedClock(NOW),
    )


class TestSubmitRun:
    def command(self, member_id: UUID, key: str) -> SubmitRunCommand:
        return SubmitRunCommand(
            member_id=member_id, distance_km=Decimal("5.25"), duration_seconds=1800,
            run_date=date(2026, 6, 1), image_key=key, source=RunSource.APP_SCREENSHOT,
        )

    def test_a_confirmed_run_is_stored(self) -> None:
        runs = FakeRunRepository()

        run = SubmitRun(submission_uow(runs)).execute(self.command(ALICE, key_for(ALICE)))

        assert run.distance_km == Decimal("5.250")
        assert run.review_status is ReviewStatus.OK
        assert runs.list_by_member(ALICE) == [run]

    def test_the_hash_is_taken_from_the_key_not_from_the_client(self) -> None:
        runs = FakeRunRepository()
        key = key_for(ALICE)

        run = SubmitRun(submission_uow(runs)).execute(self.command(ALICE, key))

        assert run.evidence_sha256 == key.rsplit("/", 1)[1].rsplit(".", 1)[0]

    def test_the_same_member_cannot_submit_the_same_image_twice(self) -> None:
        runs = FakeRunRepository()
        use_case = SubmitRun(submission_uow(runs))
        use_case.execute(self.command(ALICE, key_for(ALICE)))

        with pytest.raises(DuplicateEvidence):
            use_case.execute(self.command(ALICE, key_for(ALICE)))

        assert len(runs.list_by_member(ALICE)) == 1

    def test_another_member_reusing_an_image_is_flagged_not_refused(self) -> None:
        """Two people can legitimately photograph the same finish-line board. A human
        decides; the run is still recorded."""
        runs = FakeRunRepository([run_for(ALICE, key_for(ALICE))])
        # Same content, so the same digest, uploaded under Dao's own prefix.
        dao_key = key_for(ALICE).replace(str(ALICE), str(DAO))

        run = SubmitRun(submission_uow(runs)).execute(self.command(DAO, dao_key))

        assert run.review_status is ReviewStatus.FLAGGED
        assert len(runs.list_by_member(DAO)) == 1

    def test_a_run_cannot_be_attached_to_someone_elses_upload(self) -> None:
        runs = FakeRunRepository()

        with pytest.raises(NotAuthorized):
            SubmitRun(submission_uow(runs)).execute(self.command(DAO, key_for(ALICE)))

        assert runs.list_by_member(DAO) == []

    def test_a_malformed_key_is_refused(self) -> None:
        with pytest.raises(InvalidImage):
            SubmitRun(submission_uow()).execute(
                self.command(ALICE, f"runs/{ALICE}/not-a-hash.jpeg")
            )

    def test_confirmed_values_still_face_the_sanity_rules(self) -> None:
        """Whatever the extractor suggested, an impossible distance is refused here."""
        command = SubmitRunCommand(
            member_id=ALICE, distance_km=Decimal("500"), duration_seconds=1800,
            run_date=date(2026, 6, 1), image_key=key_for(ALICE),
            source=RunSource.APP_SCREENSHOT,
        )

        with pytest.raises(InvalidRunError):
            SubmitRun(submission_uow()).execute(command)


class TestPaceIsFlaggedNotRefused:
    """A pace outside 5–11 min/km is usually a typo or a misread screenshot, not
    cheating. The run is recorded, it still earns, and an admin decides — the same
    treatment reused evidence gets, for the same reason."""

    def command(
        self, member_id: UUID, key: str, distance_km: str, duration_seconds: int
    ) -> SubmitRunCommand:
        return SubmitRunCommand(
            member_id=member_id, distance_km=Decimal(distance_km),
            duration_seconds=duration_seconds, run_date=date(2026, 6, 1),
            image_key=key, source=RunSource.APP_SCREENSHOT,
        )

    def test_a_run_far_too_fast_is_flagged(self) -> None:
        """10 km in 25 minutes — a world record, or a distance read in miles."""
        runs = FakeRunRepository()

        run = SubmitRun(submission_uow(runs)).execute(
            self.command(ALICE, key_for(ALICE), "10", 1500)
        )

        assert run.review_status is ReviewStatus.FLAGGED
        assert run.pace_min_per_km == Decimal("2.500")
        # Recorded, not refused: the member is not arguing with a form after a run.
        assert runs.list_by_member(ALICE) == [run]

    def test_a_run_far_too_slow_is_flagged(self) -> None:
        """5 km in two hours — a duration entered in minutes instead of seconds."""
        run = SubmitRun(submission_uow()).execute(
            self.command(ALICE, key_for(ALICE), "5", 7200)
        )

        assert run.review_status is ReviewStatus.FLAGGED
        assert run.pace_min_per_km == Decimal("24.000")

    @pytest.mark.parametrize(
        ("distance_km", "duration_seconds"),
        [("10", 3000), ("10", 6600)],  # exactly 5:00/km and exactly 11:00/km
    )
    def test_the_boundary_paces_are_not_flagged(
        self, distance_km: str, duration_seconds: int
    ) -> None:
        run = SubmitRun(submission_uow()).execute(
            self.command(ALICE, key_for(ALICE), distance_km, duration_seconds)
        )

        assert run.review_status is ReviewStatus.OK

    def test_reused_evidence_and_a_bad_pace_together_still_flag_once(self) -> None:
        """Either reason is enough; there is one flagged state, not two."""
        runs = FakeRunRepository([run_for(ALICE, key_for(ALICE))])
        dao_key = key_for(ALICE).replace(str(ALICE), str(DAO))

        run = SubmitRun(submission_uow(runs)).execute(self.command(DAO, dao_key, "10", 1500))

        assert run.review_status is ReviewStatus.FLAGGED

    def test_an_ordinary_run_on_its_own_evidence_stays_ok(self) -> None:
        run = SubmitRun(submission_uow()).execute(
            self.command(ALICE, key_for(ALICE), "5", 1800)
        )

        assert run.review_status is ReviewStatus.OK

    def test_a_flagged_run_still_earns_its_points(self) -> None:
        """The flag asks for a review; it does not withhold anything. Taking the points
        back is the rejection's job, so there is one path for 'these were wrong'."""
        uow = submission_uow(campaigns=[REWARDS_CAMPAIGN])

        run = SubmitRun(uow).execute(self.command(ALICE, key_for(ALICE), "10", 1500))

        assert run.review_status is ReviewStatus.FLAGGED
        assert uow.ledger.balance(ALICE, REWARDS_CAMPAIGN.id) == Decimal("20")


class TestEvidenceUrls:
    def test_a_member_gets_short_lived_urls_for_their_own_runs(self) -> None:
        key = key_for(ALICE)
        storage = FakeImageStorage()
        runs = FakeRunRepository([run_for(ALICE, key)])

        results = ListMyRuns(runs, storage, timedelta(minutes=5)).execute(ALICE)

        assert len(results) == 1
        assert results[0].evidence_url.startswith("https://storage.test/")
        assert storage.signed == [(key, timedelta(minutes=5))]

    def test_no_url_is_ever_minted_for_another_members_image(self) -> None:
        """The IDOR check: the query is scoped first, so Dao's key is never signed."""
        storage = FakeImageStorage()
        runs = FakeRunRepository(
            [run_for(ALICE, key_for(ALICE)), run_for(DAO, key_for(DAO, PNG, "png"))]
        )

        results = ListMyRuns(runs, storage).execute(ALICE)

        assert len(results) == 1
        signed_keys = [key for key, _ in storage.signed]
        assert signed_keys == [key_for(ALICE)]
        assert all(str(DAO) not in key for key in signed_keys)

    def test_an_admin_may_see_a_members_runs(self) -> None:
        storage = FakeImageStorage()
        members = FakeMemberRepository([member(ADMIN, MemberRole.ADMIN), member(ALICE)])
        runs = FakeRunRepository([run_for(ALICE, key_for(ALICE))])

        results = ListMemberRuns(members, runs, storage).execute(ADMIN, ALICE)

        assert len(results) == 1

    def test_an_ordinary_member_may_not(self) -> None:
        storage = FakeImageStorage()
        members = FakeMemberRepository([member(DAO), member(ALICE)])
        runs = FakeRunRepository([run_for(ALICE, key_for(ALICE))])

        with pytest.raises(NotAuthorized):
            ListMemberRuns(members, runs, storage).execute(DAO, ALICE)

        assert storage.signed == []  # nothing was signed on the way to being refused


class TestExtractDraft:
    def test_a_member_can_extract_from_their_own_upload(self) -> None:
        key = key_for(ALICE)
        storage = FakeImageStorage()
        storage.put(key, JPEG, "image/jpeg")
        extractor = FakeRunExtractor()

        ExtractRunDraft(storage, extractor).execute(
            ExtractRunDraftCommand(member_id=ALICE, image_key=key)
        )

        assert extractor.calls == 1

    def test_extracting_from_someone_elses_image_is_refused(self) -> None:
        """Also stops a member spending the club's Gemini budget on other people's
        photos."""
        storage = FakeImageStorage()
        storage.put(key_for(ALICE), JPEG, "image/jpeg")
        extractor = FakeRunExtractor()

        with pytest.raises(NotAuthorized):
            ExtractRunDraft(storage, extractor).execute(
                ExtractRunDraftCommand(member_id=DAO, image_key=key_for(ALICE))
            )

        assert extractor.calls == 0


class TestPointsAreCreditedOnSubmit:
    """Without this the ledger only ever loses points: a member could earn nothing and
    never redeem anything."""

    def command(self, member_id: UUID = ALICE) -> SubmitRunCommand:
        return SubmitRunCommand(
            member_id=member_id, distance_km=Decimal("5.25"), duration_seconds=1800,
            run_date=date(2026, 6, 1), image_key=key_for(member_id),
            source=RunSource.APP_SCREENSHOT,
        )

    def test_a_run_credits_the_points_its_policy_says_it_earns(self) -> None:
        uow = submission_uow(campaigns=[REWARDS_CAMPAIGN])

        SubmitRun(uow).execute(self.command())

        # 5.25 km x 2 points/km
        assert uow.ledger.balance(ALICE, REWARDS_CAMPAIGN.id) == Decimal("10.50")

    def test_the_ledger_row_points_back_at_the_run(self) -> None:
        uow = submission_uow(campaigns=[REWARDS_CAMPAIGN])

        run = SubmitRun(uow).execute(self.command())

        entry = uow.ledger.all_entries()[0]
        assert entry.run_entry_id == run.id
        assert entry.reason is LedgerReason.RUN_EARNED

    def test_a_distance_campaign_credits_nothing(self) -> None:
        """It has no ledger at all — progress is derived from the runs themselves."""
        uow = submission_uow(campaigns=[DISTANCE_CAMPAIGN])

        SubmitRun(uow).execute(self.command())

        assert uow.ledger.all_entries() == []

    def test_the_account_lock_is_taken_before_the_ledger_is_written(self) -> None:
        """CLAUDE.md rule #5: every ledger writer takes it, earning included."""
        uow = submission_uow(campaigns=[REWARDS_CAMPAIGN])

        SubmitRun(uow).execute(self.command())

        assert uow.ledger.serialized == [(ALICE, REWARDS_CAMPAIGN.id)]

    def test_a_run_dated_outside_a_points_campaign_earns_nothing_from_it(self) -> None:
        """It still has to belong to SOME active campaign — here the distance one, whose
        window is wider — but it earns nothing from the rewards campaign it misses."""
        june_only = Campaign.create(
            code="june", name="June bonus", type=CampaignType.REDEEM_REWARD,
            starts_on=date(2026, 6, 10), ends_on=date(2026, 6, 30),
            config={"points_per_km": 1},
        )
        uow = submission_uow(campaigns=[DISTANCE_CAMPAIGN, june_only])

        SubmitRun(uow).execute(
            SubmitRunCommand(
                member_id=ALICE, distance_km=Decimal("5"), duration_seconds=1800,
                run_date=date(2026, 6, 1), image_key=key_for(ALICE),
                source=RunSource.APP_SCREENSHOT,
            )
        )

        assert uow.ledger.all_entries() == []

    def test_one_run_credits_every_points_campaign_it_falls_into(self) -> None:
        second = Campaign.create(
            code="bonus", name="Bonus month", type=CampaignType.REDEEM_REWARD,
            starts_on=date(2026, 6, 1), ends_on=date(2026, 6, 30),
            config={"points_per_km": 1},
        )
        uow = submission_uow(campaigns=[REWARDS_CAMPAIGN, second, DISTANCE_CAMPAIGN])

        SubmitRun(uow).execute(self.command())

        assert uow.ledger.balance(ALICE, REWARDS_CAMPAIGN.id) == Decimal("10.50")
        assert uow.ledger.balance(ALICE, second.id) == Decimal("5.25")

    def test_a_flagged_run_still_earns_pending_review(self) -> None:
        """One path for "these points were wrong": the admin's reject writes a reversal.
        Withholding points here would make that path unreachable."""
        runs = FakeRunRepository([run_for(ALICE, key_for(ALICE))])
        uow = submission_uow(runs=runs, campaigns=[REWARDS_CAMPAIGN])
        dao_key = key_for(ALICE).replace(str(ALICE), str(DAO))
        command = SubmitRunCommand(
            member_id=DAO, distance_km=Decimal("5.25"), duration_seconds=1800,
            run_date=date(2026, 6, 1), image_key=dao_key, source=RunSource.APP_SCREENSHOT,
        )

        run = SubmitRun(uow).execute(command)

        assert run.review_status is ReviewStatus.FLAGGED
        assert uow.ledger.balance(DAO, REWARDS_CAMPAIGN.id) == Decimal("10.50")

    def test_a_rejected_duplicate_credits_nothing(self) -> None:
        uow = submission_uow(campaigns=[REWARDS_CAMPAIGN])
        SubmitRun(uow).execute(self.command())
        before = uow.ledger.balance(ALICE, REWARDS_CAMPAIGN.id)

        with pytest.raises(DuplicateEvidence):
            SubmitRun(uow).execute(self.command())

        assert uow.ledger.balance(ALICE, REWARDS_CAMPAIGN.id) == before


class TestRunDateMustBelongToACampaign:
    """A run has to fall inside an active campaign's window, read from the database —
    so choosing a date outside this year's activity is refused at submission."""

    def command(self, run_date: date) -> SubmitRunCommand:
        return SubmitRunCommand(
            member_id=ALICE, distance_km=Decimal("5"), duration_seconds=1800,
            run_date=run_date, image_key=key_for(ALICE), source=RunSource.APP_SCREENSHOT,
        )

    def this_year(self) -> FakeRunSubmissionUnitOfWork:
        # ปีนี้: 2026-08-15 -> 2026-09-30, exactly as seeded in production.
        campaign = Campaign.create(
            code="hundred-km-2026", name="สะสม 100 กม.",
            type=CampaignType.CUMULATIVE_DISTANCE,
            starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30),
            config={"target_km": 100},
        )
        return FakeRunSubmissionUnitOfWork(
            runs=FakeRunRepository(),
            campaigns=FakeCampaignRepository([campaign]),
            ledger=FakePointsLedgerRepository(),
            clock=FixedClock(datetime(2026, 9, 1, 9, 0, tzinfo=UTC)),
        )

    def test_the_day_before_the_campaign_starts_is_refused(self) -> None:
        with pytest.raises(InvalidRunError, match="outside"):
            SubmitRun(self.this_year()).execute(self.command(date(2026, 8, 14)))

    def test_a_future_date_is_refused(self) -> None:
        with pytest.raises(InvalidRunError, match="future"):
            SubmitRun(self.this_year()).execute(self.command(date(2026, 9, 2)))

    def test_a_date_inside_the_window_is_accepted(self) -> None:
        run = SubmitRun(self.this_year()).execute(self.command(date(2026, 8, 20)))

        assert run.run_date == date(2026, 8, 20)

    def test_the_first_and_last_day_are_inside(self) -> None:
        assert SubmitRun(self.this_year()).execute(self.command(date(2026, 8, 15)))
        # (a second submission needs its own image, so this asserts the boundary only)

    def test_after_the_campaign_ends_is_refused(self) -> None:
        uow = self.this_year()
        uow.clock = FixedClock(datetime(2026, 10, 5, 9, 0, tzinfo=UTC))

        with pytest.raises(InvalidRunError, match="outside"):
            SubmitRun(uow).execute(self.command(date(2026, 10, 1)))
