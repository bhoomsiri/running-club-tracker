"""The pace band that decides whether a run gets a second pair of eyes.

Nothing here refuses anything — an implausible pace flags a run, and the run still
counts until an admin says otherwise. These tests are about the arithmetic being exact
and the boundary falling where it is documented to fall.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.entities import RunEntry, RunSource
from app.domain.pace import (
    PACE_MAX_PER_KM,
    PACE_MIN_PER_KM,
    is_pace_plausible,
    pace_min_per_km,
)

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SHA = "a" * 64


class TestTheArithmetic:
    def test_a_five_km_run_in_thirty_minutes_is_six_minutes_a_kilometre(self) -> None:
        assert pace_min_per_km(Decimal("5"), 1800) == Decimal("6")

    def test_it_stays_in_decimal_and_never_becomes_a_float(self) -> None:
        """Golden rule #6. 0.1 as a float is 0.1000000000000000055…, and a pace built on
        that cannot be compared against a boundary a member can land exactly on."""
        pace = pace_min_per_km(Decimal("5.25"), 1800)

        assert isinstance(pace, Decimal)
        assert pace == Decimal("5.714")

    def test_a_pace_that_does_not_divide_evenly_is_not_rounded_into_the_band(self) -> None:
        # 3 km in 22 minutes = 7.333… min/km, comfortably inside; the point is the tail
        # is carried, not truncated to 7.
        assert pace_min_per_km(Decimal("3"), 1320) == Decimal("7.333")


class TestTheBoundary:
    """Inclusive at both ends: a member who runs exactly 5:00/km is fast, not suspect."""

    @pytest.mark.parametrize(
        ("distance_km", "duration_seconds", "pace"),
        [
            (Decimal("10"), 3000, "5.000"),  # exactly the fast end
            (Decimal("10"), 6600, "11.000"),  # exactly the slow end
            (Decimal("10"), 4200, "7.000"),  # the middle of the band
        ],
    )
    def test_paces_inside_the_band_pass(
        self, distance_km: Decimal, duration_seconds: int, pace: str
    ) -> None:
        assert pace_min_per_km(distance_km, duration_seconds) == Decimal(pace)
        assert is_pace_plausible(distance_km, duration_seconds)

    @pytest.mark.parametrize(
        ("distance_km", "duration_seconds", "pace"),
        [
            (Decimal("10"), 2994, "4.990"),  # a hair faster than the fast end
            (Decimal("10"), 6606, "11.010"),  # a hair slower than the slow end
            (Decimal("42.195"), 3600, "1.422"),  # a marathon in an hour
            (Decimal("1"), 3600, "60.000"),  # duration typed in seconds, distance in km
        ],
    )
    def test_paces_outside_the_band_do_not(
        self, distance_km: Decimal, duration_seconds: int, pace: str
    ) -> None:
        assert pace_min_per_km(distance_km, duration_seconds) == Decimal(pace)
        assert not is_pace_plausible(distance_km, duration_seconds)

    def test_the_band_is_the_one_that_is_documented(self) -> None:
        """The numbers themselves, so widening the band is a deliberate edit rather than
        something that happens by accident to a formula."""
        fastest, slowest = PACE_MIN_PER_KM, PACE_MAX_PER_KM

        assert fastest == Decimal("5")
        assert slowest == Decimal("11")


class TestTheRunEntryProperty:
    def test_a_run_reports_its_own_pace(self) -> None:
        """Same rule, reachable from the entity — so the admin review screen and the
        submit path cannot disagree about what a run's pace was."""
        run = RunEntry.create(
            member_id=ALICE, distance_km=Decimal("5"), duration_seconds=1800,
            run_date=date(2026, 6, 1), evidence_key="runs/x/y.jpeg", evidence_sha256=SHA,
            source=RunSource.APP_SCREENSHOT, now=NOW,
        )

        assert run.pace_min_per_km == Decimal("6")
        assert is_pace_plausible(run.distance_km, run.duration_seconds)
