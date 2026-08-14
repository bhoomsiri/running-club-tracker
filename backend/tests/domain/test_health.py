from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities import Member, MemberRole, validate_display_name
from app.domain.errors import InvalidHealthRecordError, InvalidMemberError
from app.domain.health import HealthPhase, HealthRecord, bmi

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
MEMBER = uuid4()
CAMPAIGN = uuid4()


def make_record(**overrides: object) -> HealthRecord:
    kwargs: dict[str, object] = {
        "member_id": MEMBER,
        "campaign_id": CAMPAIGN,
        "phase": HealthPhase.BEFORE,
        "measured_on": date(2026, 6, 1),
        "campaign_ends_on": date(2026, 12, 31),
        "retention_days": 730,
        "now": NOW,
        "weight_kg": Decimal("70.5"),
        "height_cm": Decimal("172.5"),
    }
    kwargs.update(overrides)
    return HealthRecord.create(**kwargs)  # type: ignore[arg-type]


class TestBmi:
    def test_computed_to_one_decimal(self) -> None:
        assert bmi(Decimal("70.5"), Decimal("172.5")) == Decimal("23.7")

    @pytest.mark.parametrize(
        ("weight", "height"),
        [(None, Decimal("172.5")), (Decimal("70"), None), (None, None)],
    )
    def test_missing_input_yields_none_never_a_guess(
        self, weight: Decimal | None, height: Decimal | None
    ) -> None:
        assert bmi(weight, height) is None


class TestHealthRecord:
    def test_retention_is_frozen_from_the_campaign_end_plus_the_policy_window(self) -> None:
        record = make_record()

        # 2026-12-31 + 730 days
        assert record.retention_until == datetime(2028, 12, 30, tzinfo=UTC)

    def test_changing_the_retention_setting_does_not_touch_existing_records(self) -> None:
        old = make_record(retention_days=730)
        new = make_record(retention_days=30)

        assert old.retention_until == datetime(2028, 12, 30, tzinfo=UTC)
        assert new.retention_until == datetime(2027, 1, 30, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("field", "bad"),
        [
            ("weight_kg", Decimal("400")),
            ("weight_kg", Decimal("0")),
            ("height_cm", Decimal("300")),
            ("height_cm", Decimal("79")),
            ("resting_hr", 251),
            ("systolic", 301),
            ("diastolic", 29),
        ],
    )
    def test_implausible_measurements_are_rejected(self, field: str, bad: object) -> None:
        with pytest.raises(InvalidHealthRecordError):
            make_record(**{field: bad})

    def test_unknown_measurements_stay_none(self) -> None:
        record = make_record(weight_kg=None, height_cm=None)

        assert record.weight_kg is None
        assert record.bmi() is None

    def test_future_measurement_date_is_rejected(self) -> None:
        with pytest.raises(InvalidHealthRecordError):
            make_record(measured_on=date(2026, 6, 16))


class TestMember:
    def test_name_is_trimmed(self) -> None:
        member = Member.create(clerk_user_id="c1", display_name="  Somchai  ", now=NOW)

        assert member.display_name == "Somchai"
        assert member.role is MemberRole.MEMBER

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 121])
    def test_empty_or_overlong_names_are_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidMemberError):
            validate_display_name(bad)

    def test_exactly_120_characters_is_allowed(self) -> None:
        assert len(validate_display_name("x" * 120)) == 120

    def test_role_capabilities(self) -> None:
        assert MemberRole.MEMBER.may_view_others_health is False
        assert MemberRole.ADMIN.may_view_others_health is True
        assert MemberRole.SUPERUSER.may_view_others_health is True
        # Editing other people's records is the superuser's alone.
        assert MemberRole.ADMIN.may_edit_records is False
        assert MemberRole.SUPERUSER.may_edit_records is True
