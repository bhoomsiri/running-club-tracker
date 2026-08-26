"""Is this a pace a person could actually have run?

A screenshot read wrong, a distance typed in miles, a duration entered as minutes instead
of seconds — all of them produce a run that is arithmetically fine and physically absurd.
The bound here is deliberately wide: 5 min/km is quick club pace, 11 min/km is a gentle
jog or a brisk walk, and everything a member of this club is likely to submit sits
between them. Anything outside is not called cheating, it is called worth a look.

Nothing here refuses a run. A pace outside the band flags it for an admin, the run is
still recorded, and it still earns — the review that rejects it is what takes the points
back. One path for "these points were wrong", not two.

Decimal throughout, never float (golden rule #6): a run is 5.25 km, not
5.2500000000000002, and the pace that comes out of it is compared against a boundary a
member can land exactly on.
"""

from __future__ import annotations

from decimal import Decimal

# Inclusive. A member who runs exactly 5:00/km is fast, not implausible.
PACE_MIN_PER_KM = Decimal("5")
PACE_MAX_PER_KM = Decimal("11")

SECONDS_PER_MINUTE = Decimal("60")

# Three decimals of a minute is under a tenth of a second per kilometre — far finer than
# any real difference, and enough that a pace sitting on the boundary compares as equal
# instead of failing by a rounding tail.
PACE_PRECISION = Decimal("0.001")


def pace_min_per_km(distance_km: Decimal, duration_seconds: int) -> Decimal:
    """Minutes per kilometre.

    The caller guarantees a positive distance: `RunEntry.create()` rejects anything else
    and the `distance_sane` CHECK constraint backs it up, so there is no division by zero
    to guard against here. Guarding it anyway would mean inventing a pace for a run that
    cannot exist — golden rule #4 says represent the impossible as absent, so if that
    guarantee ever breaks this raises rather than returns a number nobody can trust.
    """
    return ((Decimal(duration_seconds) / SECONDS_PER_MINUTE) / distance_km).quantize(
        PACE_PRECISION
    )


def is_pace_plausible(distance_km: Decimal, duration_seconds: int) -> bool:
    """Whether the run sits inside the band. Both ends inclusive."""
    pace = pace_min_per_km(distance_km, duration_seconds)
    return PACE_MIN_PER_KM <= pace <= PACE_MAX_PER_KM
