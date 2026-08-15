"""The club's day, not UTC's.

Thailand is UTC+7, so between midnight and 07:00 local the UTC date is still yesterday.
Comparing a member's date against the UTC one rejects today as "in the future" — for
seven hours every night, on every form in the app that asks for a date.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.domain.calendar import CLUB_TIMEZONE, club_today

# 01:00 on the 16th in Bangkok is still 18:00 on the 15th in UTC.
EARLY_MORNING_BANGKOK = datetime(2026, 8, 15, 18, 0, tzinfo=UTC)


def test_the_club_day_is_ahead_of_utc_before_seven_am() -> None:
    assert EARLY_MORNING_BANGKOK.date() == date(2026, 8, 15)
    assert club_today(EARLY_MORNING_BANGKOK) == date(2026, 8, 16)


def test_it_agrees_with_utc_during_the_working_day() -> None:
    assert club_today(datetime(2026, 8, 16, 9, 0, tzinfo=UTC)) == date(2026, 8, 16)


def test_just_before_midnight_in_bangkok_is_still_that_day() -> None:
    almost_midnight = datetime(2026, 8, 16, 23, 59, tzinfo=CLUB_TIMEZONE)

    assert club_today(almost_midnight) == date(2026, 8, 16)


def test_the_offset_is_seven_hours() -> None:
    """Fixed, not a named zone: Thailand has had no daylight saving since 1920, so there
    is nothing for a tz database to tell us that this does not."""
    assert CLUB_TIMEZONE.utcoffset(None) == timedelta(hours=7)
