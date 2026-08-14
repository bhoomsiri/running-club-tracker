from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities import RunEntry, RunSource
from app.domain.errors import InvalidLedgerEntry, InvalidRunError, OutOfStock, RewardUnavailable
from app.domain.redemption import LedgerReason, PointsEntry, Redemption, Reward

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
MEMBER = uuid4()
CAMPAIGN = uuid4()
SHA = "a" * 64


def make_run(**overrides: object) -> RunEntry:
    kwargs: dict[str, object] = {
        "member_id": MEMBER,
        "distance_km": Decimal("5.25"),
        "duration_seconds": 1800,
        "run_date": date(2026, 6, 1),
        "evidence_key": "runs/abc.jpg",
        "evidence_sha256": SHA,
        "source": RunSource.APP_SCREENSHOT,
        "now": NOW,
    }
    kwargs.update(overrides)
    return RunEntry.create(**kwargs)  # type: ignore[arg-type]


class TestRunEntry:
    def test_valid_run_is_stored_at_millimetre_precision(self) -> None:
        assert make_run().distance_km == Decimal("5.250")

    @pytest.mark.parametrize("bad", ["0", "-1", "200.001"])
    def test_distance_out_of_range_is_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidRunError):
            make_run(distance_km=Decimal(bad))

    def test_float_distance_is_rejected_outright(self) -> None:
        with pytest.raises(InvalidRunError, match="Decimal"):
            make_run(distance_km=5.25)

    @pytest.mark.parametrize("bad", [0, -60, 86_401])
    def test_duration_out_of_range_is_rejected(self, bad: int) -> None:
        with pytest.raises(InvalidRunError):
            make_run(duration_seconds=bad)

    def test_future_run_date_is_rejected(self) -> None:
        with pytest.raises(InvalidRunError, match="future"):
            make_run(run_date=date(2026, 6, 2))

    def test_today_is_allowed(self) -> None:
        assert make_run(run_date=NOW.date()).run_date == NOW.date()

    def test_missing_evidence_key_is_rejected(self) -> None:
        with pytest.raises(InvalidRunError):
            make_run(evidence_key="   ")

    @pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "g" * 64])
    def test_malformed_evidence_hash_is_rejected(self, bad: str) -> None:
        with pytest.raises(InvalidRunError):
            make_run(evidence_sha256=bad)

    def test_entries_are_immutable(self) -> None:
        run = make_run()
        with pytest.raises(AttributeError):
            run.distance_km = Decimal("99")  # type: ignore[misc]


class TestReward:
    def test_out_of_stock_is_rejected(self) -> None:
        with pytest.raises(OutOfStock):
            Reward(uuid4(), CAMPAIGN, "Shirt", Decimal("50"), 0, True).ensure_redeemable()

    def test_inactive_is_rejected(self) -> None:
        with pytest.raises(RewardUnavailable):
            Reward(uuid4(), CAMPAIGN, "Shirt", Decimal("50"), 5, False).ensure_redeemable()


class TestPointsEntry:
    def test_spending_is_a_negative_row_referencing_the_redemption(self) -> None:
        reward = Reward(uuid4(), CAMPAIGN, "Shirt", Decimal("50"), 1, True)
        redemption = Redemption.create(member_id=MEMBER, reward=reward, now=NOW)

        entry = PointsEntry.for_redemption(redemption=redemption, now=NOW)

        assert entry.delta == Decimal("-50.00")
        assert entry.reason is LedgerReason.REDEEMED
        assert entry.redemption_id == redemption.id
        assert entry.run_entry_id is None

    def test_earning_references_the_run(self) -> None:
        run_id = uuid4()
        entry = PointsEntry.for_run(
            member_id=MEMBER, campaign_id=CAMPAIGN, points=Decimal("5.25"),
            run_entry_id=run_id, now=NOW,
        )

        assert entry.delta == Decimal("5.25")
        assert entry.run_entry_id == run_id
        assert entry.redemption_id is None

    def test_earning_zero_or_negative_points_is_rejected(self) -> None:
        with pytest.raises(InvalidLedgerEntry):
            PointsEntry.for_run(
                member_id=MEMBER, campaign_id=CAMPAIGN, points=Decimal("0"),
                run_entry_id=uuid4(), now=NOW,
            )

    def test_reason_and_reference_must_agree(self) -> None:
        """Same rule as the ck_points_ledger_ref_matches_reason CHECK — a row the
        domain builds can never be one the DB rejects."""
        with pytest.raises(InvalidLedgerEntry):
            PointsEntry(uuid4(), MEMBER, CAMPAIGN, Decimal("5"), LedgerReason.RUN_EARNED,
                        None, None, NOW)
        with pytest.raises(InvalidLedgerEntry):
            PointsEntry(uuid4(), MEMBER, CAMPAIGN, Decimal("-5"), LedgerReason.REDEEMED,
                        uuid4(), None, NOW)
        with pytest.raises(InvalidLedgerEntry):
            PointsEntry(uuid4(), MEMBER, CAMPAIGN, Decimal("5"), LedgerReason.ADJUSTMENT,
                        uuid4(), uuid4(), NOW)

    def test_adjustment_may_reference_one_source_or_neither(self) -> None:
        PointsEntry(uuid4(), MEMBER, CAMPAIGN, Decimal("5"), LedgerReason.ADJUSTMENT,
                    None, None, NOW)
        PointsEntry(uuid4(), MEMBER, CAMPAIGN, Decimal("-5"), LedgerReason.REVERSAL,
                    uuid4(), None, NOW)
