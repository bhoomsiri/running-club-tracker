"""What day it is, from the club's point of view.

Every "not in the future" rule in this app compares a date the member typed against the
current date — and the member types the date on their phone, in Thailand. Comparing it
against the UTC date rejects a run submitted at 2am in Bangkok, because there it is
still yesterday in UTC; the member is told that today is in the future.

A fixed offset rather than a named zone: Thailand has been UTC+7 with no daylight saving
since 1920, so the offset is exact, and it keeps the domain free of the tz database that
`zoneinfo` would need shipping on Windows.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

CLUB_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Bangkok")


def club_today(now: datetime) -> date:
    """The date it is for the club right now, whatever timezone `now` carries."""
    return now.astimezone(CLUB_TIMEZONE).date()
