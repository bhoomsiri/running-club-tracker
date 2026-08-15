"""The second must-cover case: health data cannot be written without active consent."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.grant_consent import GrantConsent, GrantConsentCommand
from app.application.use_cases.save_health_record import (
    SaveHealthRecord,
    SaveHealthRecordCommand,
)
from app.application.use_cases.withdraw_consent import WithdrawConsent, WithdrawConsentCommand
from app.domain.campaign import Campaign, CampaignType
from app.domain.consent import Consent, ConsentPurpose
from app.domain.errors import (
    ConsentRequired,
    InvalidCampaignError,
    InvalidHealthRecordError,
)
from app.domain.health import HealthPhase
from tests.fakes.fake_health_uow import ImmediateConsentRepository
from tests.fakes.fake_uow import FixedClock
from tests.fakes.repositories import FakeCampaignRepository, FakeHealthRepository

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CURRENT_VERSION = "v2"
RETENTION_DAYS = 730

CAMPAIGN = Campaign.create(
    id=UUID("11111111-1111-1111-1111-111111111111"),
    code="100km", name="100 km", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), config={"target_km": 100},
)


def consent(version: str = CURRENT_VERSION, *, withdrawn: bool = False) -> Consent:
    granted = Consent.grant(
        member_id=ALICE, purpose=ConsentPurpose.HEALTH_DATA, version=version, now=NOW
    )
    return granted.withdraw(NOW) if withdrawn else granted


def build(
    consents: list[Consent] | None = None,
) -> tuple[SaveHealthRecord, ImmediateConsentRepository, FakeHealthRepository]:
    consent_repo = ImmediateConsentRepository(consents or [])
    health = FakeHealthRepository()
    use_case = SaveHealthRecord(
        consents=consent_repo,
        campaigns=FakeCampaignRepository([CAMPAIGN]),
        health=health,
        clock=FixedClock(NOW),
        consent_version=CURRENT_VERSION,
        retention_days=RETENTION_DAYS,
    )
    return use_case, consent_repo, health


def command(**overrides: object) -> SaveHealthRecordCommand:
    kwargs: dict[str, object] = {
        "member_id": ALICE,
        "campaign_id": CAMPAIGN.id,
        "phase": HealthPhase.BEFORE,
        "measured_on": date(2026, 6, 1),
        "weight_kg": Decimal("70.5"),
        "height_cm": Decimal("172.5"),
    }
    kwargs.update(overrides)
    return SaveHealthRecordCommand(**kwargs)  # type: ignore[arg-type]


class TestConsentGate:
    def test_no_consent_at_all_is_rejected(self) -> None:
        use_case, _, health = build()

        with pytest.raises(ConsentRequired):
            use_case.execute(command())

        assert health.list_by_member(ALICE) == []

    def test_withdrawn_consent_is_rejected(self) -> None:
        use_case, _, health = build([consent(withdrawn=True)])

        with pytest.raises(ConsentRequired):
            use_case.execute(command())

        assert health.list_by_member(ALICE) == []

    def test_consent_to_superseded_wording_is_rejected(self) -> None:
        """Agreeing to v1 is not agreeing to v2 — the member must be asked again."""
        use_case, _, health = build([consent(version="v1")])

        with pytest.raises(ConsentRequired):
            use_case.execute(command())

        assert health.list_by_member(ALICE) == []

    def test_active_current_consent_is_accepted(self) -> None:
        use_case, _, health = build([consent()])

        record = use_case.execute(command())

        assert record.weight_kg == Decimal("70.5")
        assert health.list_by_member(ALICE) == [record]

    def test_the_gate_holds_again_after_withdrawal(self) -> None:
        use_case, consents, health = build([consent()])
        use_case.execute(command())

        WithdrawConsent(consents, FixedClock(NOW)).execute(WithdrawConsentCommand(ALICE))

        with pytest.raises(ConsentRequired):
            use_case.execute(command(phase=HealthPhase.AFTER))
        # Withdrawal stops new processing; it does not delete what is already stored.
        assert len(health.list_by_member(ALICE)) == 1


class TestRecordContent:
    def test_retention_is_frozen_from_the_campaign_end(self) -> None:
        use_case, _, _ = build([consent()])

        record = use_case.execute(command())

        assert record.retention_until == datetime(2028, 12, 30, tzinfo=UTC)

    def test_unknown_measurements_stay_none(self) -> None:
        use_case, _, _ = build([consent()])

        record = use_case.execute(command(weight_kg=None, systolic=None))

        assert record.weight_kg is None
        assert record.systolic is None

    def test_correcting_a_measurement_replaces_the_same_record(self) -> None:
        use_case, _, health = build([consent()])
        first = use_case.execute(command(weight_kg=Decimal("70.5")))

        second = use_case.execute(command(weight_kg=Decimal("69.0")))

        assert second.id == first.id  # same record, corrected
        assert health.list_by_member(ALICE) == [second]

    def test_before_and_after_are_separate_records(self) -> None:
        use_case, _, health = build([consent()])

        use_case.execute(command(phase=HealthPhase.BEFORE))
        use_case.execute(command(phase=HealthPhase.AFTER, weight_kg=Decimal("68.0")))

        assert len(health.list_by_member(ALICE)) == 2

    def test_unknown_campaign_is_rejected(self) -> None:
        use_case, _, _ = build([consent()])

        with pytest.raises(InvalidCampaignError):
            use_case.execute(command(campaign_id=uuid4()))


class TestConsentLifecycle:
    def test_granting_records_the_current_version(self) -> None:
        consents = ImmediateConsentRepository()

        granted = GrantConsent(consents, FixedClock(NOW), CURRENT_VERSION).execute(
            GrantConsentCommand(ALICE)
        )

        assert granted.version == CURRENT_VERSION
        assert granted.is_active(CURRENT_VERSION)

    def test_granting_twice_is_idempotent(self) -> None:
        consents = ImmediateConsentRepository()
        use_case = GrantConsent(consents, FixedClock(NOW), CURRENT_VERSION)

        first = use_case.execute(GrantConsentCommand(ALICE))
        second = use_case.execute(GrantConsentCommand(ALICE))

        assert first.id == second.id
        assert len(consents.all_consents()) == 1

    def test_re_granting_after_a_version_bump_supersedes_the_old_agreement(self) -> None:
        consents = ImmediateConsentRepository([consent(version="v1")])

        granted = GrantConsent(consents, FixedClock(NOW), "v2").execute(
            GrantConsentCommand(ALICE)
        )

        assert granted.version == "v2"
        # The old agreement is closed, not overwritten: what was agreed to, and until
        # when, stays on the record.
        history = consents.all_consents()
        assert len(history) == 2
        old = next(c for c in history if c.version == "v1")
        assert old.withdrawn_at == NOW

    def test_withdrawing_when_nothing_is_active_is_not_an_error(self) -> None:
        consents = ImmediateConsentRepository()

        assert WithdrawConsent(consents, FixedClock(NOW)).execute(
            WithdrawConsentCommand(ALICE)
        ) is None

    def test_withdrawal_is_recorded_not_deleted(self) -> None:
        consents = ImmediateConsentRepository([consent()])

        withdrawn = WithdrawConsent(consents, FixedClock(NOW)).execute(
            WithdrawConsentCommand(ALICE)
        )

        assert withdrawn is not None
        assert withdrawn.withdrawn_at == NOW
        assert len(consents.all_consents()) == 1
        assert consents.get_current(ALICE, ConsentPurpose.HEALTH_DATA) is None


OTHER_CAMPAIGN = Campaign.create(
    id=UUID("22222222-2222-2222-2222-222222222222"),
    code="other", name="Other activity", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), config={"target_km": 50},
)


class TestMeasurementOrder:
    """An 'after' dated before its 'before' makes the comparison read backwards: the
    member is shown a BMI change with the wrong sign and told it is their progress."""

    def use_case(self) -> SaveHealthRecord:
        return SaveHealthRecord(
            consents=ImmediateConsentRepository([consent()]),
            campaigns=FakeCampaignRepository([CAMPAIGN, OTHER_CAMPAIGN]),
            health=FakeHealthRepository(),
            clock=FixedClock(NOW),
            consent_version=CURRENT_VERSION,
            retention_days=RETENTION_DAYS,
        )

    def save(
        self,
        use_case: SaveHealthRecord,
        phase: HealthPhase,
        measured_on: date,
        campaign_id: UUID = CAMPAIGN.id,
    ) -> None:
        use_case.execute(
            command(phase=phase, measured_on=measured_on, campaign_id=campaign_id)
        )

    def test_after_earlier_than_before_is_rejected(self) -> None:
        use_case = self.use_case()
        self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 10))

        with pytest.raises(InvalidHealthRecordError):
            self.save(use_case, HealthPhase.AFTER, date(2026, 6, 9))

    def test_after_on_the_same_day_is_allowed(self) -> None:
        """Measuring both on the last day of the activity is ordinary."""
        use_case = self.use_case()
        self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 10))

        self.save(use_case, HealthPhase.AFTER, date(2026, 6, 10))

    def test_after_later_than_before_is_allowed(self) -> None:
        use_case = self.use_case()
        self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 10))

        self.save(use_case, HealthPhase.AFTER, date(2026, 6, 14))

    def test_the_rule_holds_from_the_other_direction_too(self) -> None:
        """Re-saving 'before' with a date after an existing 'after' is the same
        inconsistency arriving the other way round, and leaves the same broken pair."""
        use_case = self.use_case()
        self.save(use_case, HealthPhase.AFTER, date(2026, 6, 10))

        with pytest.raises(InvalidHealthRecordError):
            self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 14))

    def test_the_first_record_has_nothing_to_compare_against(self) -> None:
        """Recording 'after' first is allowed — members do not always start at the
        beginning."""
        self.save(self.use_case(), HealthPhase.AFTER, date(2026, 6, 14))

    def test_nothing_is_written_when_the_order_is_rejected(self) -> None:
        """The refusal has to happen before the upsert, or a bad date would overwrite
        the member's existing record on its way to raising."""
        use_case = self.use_case()
        self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 10))
        self.save(use_case, HealthPhase.AFTER, date(2026, 6, 14))

        with pytest.raises(InvalidHealthRecordError):
            self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 15))

        stored = use_case._health.list_by_member(ALICE)
        before = next(r for r in stored if r.phase is HealthPhase.BEFORE)
        assert before.measured_on == date(2026, 6, 10), "the old record must be intact"

    def test_another_campaign_does_not_constrain_this_one(self) -> None:
        """The rule is per campaign: dates in one activity say nothing about another
        that ran at a different time."""
        use_case = self.use_case()
        self.save(use_case, HealthPhase.BEFORE, date(2026, 6, 10))

        self.save(use_case, HealthPhase.AFTER, date(2026, 6, 1), OTHER_CAMPAIGN.id)
