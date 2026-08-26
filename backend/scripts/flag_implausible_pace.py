"""Flag runs already in the database whose pace falls outside 5–11 min/km.

The pace check flags new submissions from the moment it ships. Runs submitted before
that never met it, so this walks them once. It is a backfill, not a policy — the policy
lives in `app.domain.pace`, and this imports it rather than expressing the same rule in
SQL. Two spellings of one rule is how a backfill and a live path end up disagreeing about
which runs are suspect.

Narrow on purpose:

  - only `review_status = 'ok'` runs are considered. A run already `flagged` (the reused
    evidence case) is left alone — it is flagged either way, and re-stamping it would
    lose nothing but say something happened that did not. A `rejected` run has had a
    human decision made about it, and this is not one.
  - **points are not touched.** A flagged run still earns, exactly as a newly submitted
    one does; the review that rejects it is what reconciles the points back down. This
    script does not read or write `points_ledger` at all.
  - the only transition it can make is `ok -> flagged`, verified from both directions
    before anything is committed.

Same guards as the other one-offs: `--expect-host` has to match the host in
DATABASE_URL, and it rolls back unless `--commit` is passed.

    python scripts/flag_implausible_pace.py --expect-host ep-xxxx.neon.tech
    python scripts/flag_implausible_pace.py --expect-host ep-xxxx.neon.tech --commit
"""

from __future__ import annotations

import argparse
import sys
import uuid
from decimal import Decimal
from typing import Any, NamedTuple

from sqlalchemy import Connection, create_engine, make_url, text

from app.config import get_settings
from app.domain.pace import PACE_MAX_PER_KM, PACE_MIN_PER_KM, is_pace_plausible, pace_min_per_km


class Candidate(NamedTuple):
    id: uuid.UUID
    distance_km: Decimal
    duration_seconds: int
    pace: Decimal


def main() -> int:
    args = _parse_args()
    url = make_url(get_settings().database_url)

    # No password, ever — not even on a terminal nobody else is reading.
    print(f"target   : {url.username}@{url.host}/{url.database}")
    print(f"expected : {args.expect_host}")
    if url.host != args.expect_host:
        print("\nREFUSED: DATABASE_URL points somewhere else. Nothing was run.")
        return 2
    print(f"mode     : {'COMMIT' if args.commit else 'dry run (rolls back)'}")
    print(f"band     : {PACE_MIN_PER_KM}–{PACE_MAX_PER_KM} min/km, inclusive\n")

    engine = create_engine(url, pool_pre_ping=True, future=True)
    with engine.connect() as connection, connection.begin() as transaction:
        before = _counts(connection)
        _print_counts("before", before)

        candidates = _implausible(connection)
        _print_candidates(candidates)

        flipped = 0
        if candidates:
            flipped = connection.execute(
                text(
                    "UPDATE run_entry SET review_status = 'flagged'"
                    " WHERE id = ANY(:ids) AND review_status = 'ok'"
                ),
                {"ids": [candidate.id for candidate in candidates]},
            ).rowcount
        print(f"\nflipped  : {flipped} run(s) ok -> flagged")

        after = _counts(connection)
        _print_counts("after", after)

        failures = _verify(before, after, candidates, flipped, connection)
        _print_verification(failures)
        if failures:
            # Rolls back on the way out. Raising rather than returning, so a caller that
            # ignores exit codes still cannot mistake this for success.
            raise VerificationFailed(f"{len(failures)} check(s) failed; nothing was committed")

        if not args.commit:
            transaction.rollback()
            print("\nDry run: rolled back. Re-run with --commit to apply.")
            return 0

    print("\nCommitted.")
    return 0


class VerificationFailed(RuntimeError):
    pass


def _implausible(connection: Connection) -> list[Candidate]:
    """The 'ok' runs whose pace is outside the band — decided in Python, by the domain.

    The database returns the two numbers; `is_pace_plausible` decides. At this club's
    size the whole table fits in memory many times over, and paying that to keep one
    definition of the rule is the trade this script exists to make.
    """
    rows = connection.execute(
        text(
            "SELECT id, distance_km, duration_seconds FROM run_entry"
            " WHERE review_status = 'ok' ORDER BY created_at"
        )
    ).all()
    return [
        Candidate(
            row.id, row.distance_km, row.duration_seconds,
            pace_min_per_km(row.distance_km, row.duration_seconds),
        )
        for row in rows
        if not is_pace_plausible(row.distance_km, row.duration_seconds)
    ]


def _counts(connection: Connection) -> dict[str, Any]:
    counts = {
        status: connection.execute(
            text("SELECT count(*) FROM run_entry WHERE review_status = :s"), {"s": status}
        ).scalar_one()
        for status in ("ok", "flagged", "rejected")
    }
    counts["total"] = connection.execute(text("SELECT count(*) FROM run_entry")).scalar_one()
    # Every run's status, so "nothing else moved" is checked per row rather than in
    # aggregate — two runs swapping status would leave the totals identical.
    counts["by_id"] = {
        str(row.id): row.review_status
        for row in connection.execute(text("SELECT id, review_status FROM run_entry")).all()
    }
    return counts


def _verify(
    before: dict[str, Any],
    after: dict[str, Any],
    candidates: list[Candidate],
    flipped: int,
    connection: Connection,
) -> list[str]:
    failures = []

    if flipped != len(candidates):
        failures.append(f"found {len(candidates)} implausible run(s) but flipped {flipped}")

    if after["total"] != before["total"]:
        failures.append(f"run_entry count changed: {before['total']} -> {after['total']}")
    if after["rejected"] != before["rejected"]:
        failures.append(
            f"rejected changed: {before['rejected']} -> {after['rejected']} — a human decision"
        )
    if after["ok"] != before["ok"] - flipped:
        failures.append(f"ok should be {before['ok'] - flipped}, found {after['ok']}")
    expected_flagged = before["flagged"] + flipped
    if after["flagged"] != expected_flagged:
        failures.append(f"flagged should be {expected_flagged}, found {after['flagged']}")

    # The only transition allowed is ok -> flagged, checked row by row.
    expected_flips = {str(candidate.id) for candidate in candidates}
    for run_id, was in before["by_id"].items():
        now = after["by_id"].get(run_id)
        if now is None:
            failures.append(f"run {run_id} disappeared")
        elif now == was:
            continue
        elif (was, now) != ("ok", "flagged"):
            failures.append(f"run {run_id}: {was} -> {now} is not an allowed transition")
        elif run_id not in expected_flips:
            failures.append(f"run {run_id} was flipped but is not one of the implausible runs")

    changed = {
        run_id
        for run_id, was in before["by_id"].items()
        if after["by_id"].get(run_id) != was
    }
    for missing in expected_flips - changed:
        failures.append(f"run {missing} is implausible but was not flagged")

    # And every run left as 'ok' really is inside the band.
    if _implausible(connection):
        failures.append("implausible runs are still marked ok")

    return failures


def _print_counts(label: str, counts: dict[str, Any]) -> None:
    print(f"{label}:")
    for status in ("ok", "flagged", "rejected"):
        print(f"  {status:<10} {counts[status]:>4}")
    print(f"  {'total':<10} {counts['total']:>4}")


def _print_candidates(candidates: list[Candidate]) -> None:
    print(f"\nimplausible pace among 'ok' runs: {len(candidates)}")
    for candidate in candidates:
        print(
            f"  {candidate.id}  {candidate.distance_km:>8} km"
            f"  {candidate.duration_seconds:>6} s"
            f"  {candidate.pace:>8} min/km"
        )


def _print_verification(failures: list[str]) -> None:
    print("\nverification:")
    if not failures:
        print("  all checks passed")
        return
    for failure in failures:
        print(f"  FAIL  {failure}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-host",
        required=True,
        help="the host DATABASE_URL must point at; refuses to run against any other",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="apply the flags. Without it everything runs and is then rolled back.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
