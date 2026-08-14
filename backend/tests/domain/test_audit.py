"""Golden rule #8, enforced rather than trusted: sensitive values must not reach a log."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.audit import AuditAction, AuditEntry
from app.domain.consent import Consent, ConsentPurpose
from app.domain.errors import InvalidAuditEntry, InvalidConsentError

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
ACTOR = uuid4()
SUBJECT = uuid4()


def entry(detail: dict[str, object]) -> AuditEntry:
    return AuditEntry.create(
        actor_member_id=ACTOR,
        action=AuditAction.VIEW_HEALTH,
        subject_member_id=SUBJECT,
        detail=detail,
        now=NOW,
    )


class TestAuditDetail:
    def test_context_values_are_kept(self) -> None:
        assert entry({"campaign_count": 2, "note": "quarterly review"}).detail == {
            "campaign_count": 2,
            "note": "quarterly review",
        }

    def test_uuids_are_stringified_for_json_storage(self) -> None:
        campaign_id = uuid4()

        assert entry({"campaign_id": campaign_id}).detail == {"campaign_id": str(campaign_id)}

    @pytest.mark.parametrize(
        "key", ["weight_kg", "systolic", "bmi", "email", "token", "Weight_KG"]
    )
    def test_sensitive_field_names_are_refused(self, key: str) -> None:
        with pytest.raises(InvalidAuditEntry, match="sensitive"):
            entry({key: 70})

    def test_measurements_are_refused_by_type(self) -> None:
        # A Decimal is almost always a measurement.
        with pytest.raises(InvalidAuditEntry):
            entry({"reading": Decimal("70.5")})

    def test_dumping_a_whole_record_is_refused(self) -> None:
        with pytest.raises(InvalidAuditEntry):
            entry({"record": {"weight_kg": 70.5}})

    def test_an_entry_without_detail_is_fine(self) -> None:
        assert AuditEntry.create(
            actor_member_id=ACTOR, action=AuditAction.EDIT_MEMBER, now=NOW
        ).detail == {}


class TestConsent:
    def test_active_requires_the_current_wording(self) -> None:
        granted = Consent.grant(
            member_id=SUBJECT, purpose=ConsentPurpose.HEALTH_DATA, version="v1", now=NOW
        )

        assert granted.is_active("v1") is True
        assert granted.is_active("v2") is False

    def test_withdrawn_consent_is_never_active(self) -> None:
        granted = Consent.grant(
            member_id=SUBJECT, purpose=ConsentPurpose.HEALTH_DATA, version="v1", now=NOW
        )

        assert granted.withdraw(NOW).is_active("v1") is False

    def test_withdrawing_twice_is_refused(self) -> None:
        granted = Consent.grant(
            member_id=SUBJECT, purpose=ConsentPurpose.HEALTH_DATA, version="v1", now=NOW
        )

        with pytest.raises(InvalidConsentError):
            granted.withdraw(NOW).withdraw(NOW)

    def test_an_empty_version_is_refused(self) -> None:
        with pytest.raises(InvalidConsentError):
            Consent.grant(
                member_id=SUBJECT, purpose=ConsentPurpose.HEALTH_DATA, version=" ", now=NOW
            )
