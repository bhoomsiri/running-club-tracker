"""Read calories and steps off the evidence images of runs submitted before we asked.

`calories_burned` and `steps` arrived in migration 0009. Runs submitted before it hold
NULL in both, and their screenshots are still in the bucket with the numbers printed on
them — so this walks those runs once and asks Gemini what the picture says.

The same extractor as the submit flow, not a second one. Its clamps are what keep an
untrusted model's output inside the CHECK constraints, and a copy of them here would be a
copy that drifts.

Narrow on purpose, and the narrowness is the point:

  - **only `calories_burned` and `steps`, and only where they are NULL.** A value the
    member typed or confirmed is never overwritten.
  - **distance and duration are never re-extracted.** The member confirmed those at
    submission and they are what the run's points and its pace are made of; a model
    disagreeing with them a month later is not new information, it is a silent edit to a
    result. The draft's distance and duration are read and thrown away.
  - **`review_status` is not touched**, and neither is `points_ledger`. Nothing here can
    change what anyone has earned.
  - rejected runs are skipped: they show on no screen, and a Gemini call for one is money
    spent on a number nobody will read.
  - a screenshot that carries no calorie figure — the ordinary case — leaves the column
    NULL. Nothing is guessed to fill a gap (golden rule #4).

**Committed in batches, unlike the other one-offs.** Those finish in a second and one
transaction is right for them. This one spends a second or two per image, so a single
transaction would hold a connection open for half an hour and lose every extraction if
anything went wrong at minute 29. A batch is verified whole and then committed, and
because the query only selects NULLs, re-running after a crash picks up where it stopped.

**A dry run costs the same Gemini calls as a real one.** It reads every image and then
rolls back. Use `--limit` to try a handful first.

    python scripts/backfill_activity.py --expect-host ep-xxxx.neon.tech --limit 5
    python scripts/backfill_activity.py --expect-host ep-xxxx.neon.tech --commit
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import NamedTuple

from sqlalchemy import Connection, create_engine, make_url, text

from app.adapters.extraction.gemini_extractor import GeminiExtractor
from app.adapters.storage.s3_image_storage import S3ImageStorage
from app.application.ports.image_storage import ImageStorage
from app.application.ports.run_extractor import RunExtractor
from app.config import get_settings
from app.domain.errors import EvidenceNotFound, InvalidImage
from app.domain.evidence import detect_image_kind

BATCH_SIZE = 20


class Candidate(NamedTuple):
    id: uuid.UUID
    evidence_key: str
    calories_burned: int | None
    steps: int | None


class Filled(NamedTuple):
    """What a single image turned out to be worth. Values, not printed anywhere."""

    calories_burned: int | None
    steps: int | None

    @property
    def is_empty(self) -> bool:
        return self.calories_burned is None and self.steps is None


class Tally:
    def __init__(self) -> None:
        self.scanned = 0
        self.calories_filled = 0
        self.steps_filled = 0
        self.nothing_found = 0
        self.unreadable: list[tuple[uuid.UUID, str]] = []


def main() -> int:
    args = _parse_args()
    settings = get_settings()
    url = make_url(settings.database_url)

    # No password, ever — not even on a terminal nobody else is reading.
    print(f"target   : {url.username}@{url.host}/{url.database}")
    print(f"expected : {args.expect_host}")
    if url.host != args.expect_host:
        print("\nREFUSED: DATABASE_URL points somewhere else. Nothing was run.")
        return 2
    print(f"mode     : {'COMMIT' if args.commit else 'dry run (rolls back each batch)'}")
    print(f"bucket   : {settings.s3_bucket}")
    print("note     : a dry run spends the same Gemini calls as a real one\n")

    storage = S3ImageStorage(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    extractor = GeminiExtractor(api_key=settings.gemini_api_key)

    engine = create_engine(url, pool_pre_ping=True, future=True)
    tally = Tally()

    with engine.connect() as connection:
        # Taken once, outside any transaction: every check below is "did anything move
        # that should not have", and the answer is measured against the table as it was
        # before the first batch.
        before = _snapshot(connection)
        candidates = _candidates(connection, args.limit)
        print(f"runs     : {len(candidates)} with a NULL to fill\n")
        if not candidates:
            print("Nothing to do.")
            return 0

        for start in range(0, len(candidates), args.batch_size):
            batch = candidates[start : start + args.batch_size]
            number = start // args.batch_size + 1
            total = -(-len(candidates) // args.batch_size)
            print(f"batch {number}/{total} ({len(batch)} run(s))")

            with connection.begin() as transaction:
                written = _process(batch, connection, storage, extractor, tally)

                failures = _verify(before, _snapshot(connection), written)
                if failures:
                    _print_verification(failures)
                    # Rolls back on the way out. Raising rather than returning, so a
                    # caller that ignores exit codes cannot mistake this for success.
                    raise VerificationFailed(
                        f"{len(failures)} check(s) failed in batch {number}; it was not committed"
                    )

                if not args.commit:
                    transaction.rollback()
                    # The next batch is measured against `before` either way: nothing was
                    # kept, so the table has not moved.
                    print("  rolled back (dry run)")
                else:
                    # Committed rows become the new baseline, or the next batch's check
                    # would report them as unexpected changes.
                    before.update({str(run_id): values for run_id, values in written.items()})
                    print(f"  committed {len(written)} row(s)")

    _print_tally(tally, len(candidates))
    print("\nDry run: nothing was kept." if not args.commit else "\nCommitted.")
    return 0


class VerificationFailed(RuntimeError):
    pass


def _process(
    batch: list[Candidate],
    connection: Connection,
    storage: ImageStorage,
    extractor: RunExtractor,
    tally: Tally,
) -> dict[uuid.UUID, tuple[int | None, int | None]]:
    """Read each image and write back only the columns that were NULL.

    Returns what each row should now hold, which is what the verification is checked
    against — not what the model said, but what this intended to write.
    """
    written: dict[uuid.UUID, tuple[int | None, int | None]] = {}

    for candidate in batch:
        try:
            filled = _read(candidate, storage, extractor)
        except Unreadable as error:
            tally.unreadable.append((candidate.id, str(error)))
            continue

        tally.scanned += 1
        # Only where it was NULL. `filled` already carries None for anything the model
        # could not read, and COALESCE would be the same rule spelled in SQL — doing it
        # here keeps "never overwrite" in one place with the decision it belongs to.
        calories = candidate.calories_burned if candidate.calories_burned is not None else (
            filled.calories_burned
        )
        steps = candidate.steps if candidate.steps is not None else filled.steps

        if (calories, steps) == (candidate.calories_burned, candidate.steps):
            tally.nothing_found += 1
            continue

        if calories != candidate.calories_burned:
            tally.calories_filled += 1
        if steps != candidate.steps:
            tally.steps_filled += 1

        connection.execute(
            text(
                "UPDATE run_entry SET calories_burned = :calories, steps = :steps"
                " WHERE id = :id AND review_status <> 'rejected'"
            ),
            {"calories": calories, "steps": steps, "id": candidate.id},
        )
        written[candidate.id] = (calories, steps)
        # The id and which columns were filled — never the numbers, and never the image
        # (golden rule #8 keeps values out of logs; this is the same instinct applied to
        # a terminal somebody may paste into a chat).
        filled_names = [
            name
            for name, changed in (
                ("calories", calories != candidate.calories_burned),
                ("steps", steps != candidate.steps),
            )
            if changed
        ]
        print(f"  {candidate.id}  filled {' + '.join(filled_names)}")

    return written


class Unreadable(RuntimeError):
    pass


def _read(
    candidate: Candidate, storage: ImageStorage, extractor: RunExtractor
) -> Filled:
    try:
        image = storage.get(candidate.evidence_key)
    except EvidenceNotFound as error:
        # The object is gone — an erasure, or an upload that never completed. Counted and
        # skipped; the row keeps its NULLs, which is the truth about it.
        raise Unreadable("evidence image not in the bucket") from error
    except Exception as error:
        raise Unreadable(f"storage error: {type(error).__name__}") from error

    try:
        kind = detect_image_kind(image)
    except InvalidImage as error:
        raise Unreadable(f"not a usable image: {error}") from error

    draft = extractor.extract(image, kind.value)
    # distance_km, duration_seconds and run_date are on the draft and are deliberately
    # ignored. See the module docstring: re-reading them would be a silent edit to a
    # result the member already confirmed.
    return Filled(calories_burned=draft.calories_burned, steps=draft.steps)


def _candidates(connection: Connection, limit: int | None) -> list[Candidate]:
    """Runs that still count and are missing at least one of the two numbers.

    `review_status <> 'rejected'` is `valid_runs_of` expressed for the database — the one
    place in this script where a domain rule is restated, and it is restated rather than
    imported because loading every run into memory to filter two dozen would be the wrong
    trade here. `counts_toward_earning` is its single sentence: a rejected run counts for
    nothing, a flagged one is still awaiting a decision.
    """
    rows = connection.execute(
        text(
            "SELECT id, evidence_key, calories_burned, steps FROM run_entry"
            " WHERE review_status <> 'rejected'"
            "   AND (calories_burned IS NULL OR steps IS NULL)"
            " ORDER BY created_at"
            + (" LIMIT :limit" if limit is not None else "")
        ),
        {"limit": limit} if limit is not None else {},
    ).all()
    return [
        Candidate(row.id, row.evidence_key, row.calories_burned, row.steps) for row in rows
    ]


def _snapshot(connection: Connection) -> dict[str, tuple[int | None, int | None]]:
    """Only the two columns this may write. Everything else is checked separately, below,
    so a change to a third column is caught rather than simply not looked at."""
    return {
        str(row.id): (row.calories_burned, row.steps)
        for row in connection.execute(
            text("SELECT id, calories_burned, steps FROM run_entry")
        ).all()
    }


def _verify(
    before: dict[str, tuple[int | None, int | None]],
    after: dict[str, tuple[int | None, int | None]],
    written: dict[uuid.UUID, tuple[int | None, int | None]],
) -> list[str]:
    failures = []

    if set(after) != set(before):
        failures.append("the set of runs changed while the batch was running")

    expected = {str(run_id): values for run_id, values in written.items()}
    for run_id, was in before.items():
        now = after.get(run_id)
        if now is None or now == was:
            continue
        if run_id not in expected:
            failures.append(f"run {run_id} changed but was not one this batch wrote")
            continue
        if now != expected[run_id]:
            failures.append(f"run {run_id} does not hold what the batch meant to write")
        # The rule the whole script exists to keep.
        was_calories, was_steps = was
        now_calories, now_steps = now
        if was_calories is not None and now_calories != was_calories:
            failures.append(f"run {run_id}: an existing calorie figure was overwritten")
        if was_steps is not None and now_steps != was_steps:
            failures.append(f"run {run_id}: an existing step count was overwritten")

    for run_id in expected:
        if after.get(run_id) == before.get(run_id):
            failures.append(f"run {run_id} was written but the row did not change")

    return failures


def _print_tally(tally: Tally, candidates: int) -> None:
    print("\nresult:")
    print(f"  {'candidates':<24} {candidates:>4}")
    print(f"  {'images scanned':<24} {tally.scanned:>4}")
    print(f"  {'calories filled':<24} {tally.calories_filled:>4}")
    print(f"  {'steps filled':<24} {tally.steps_filled:>4}")
    print(f"  {'nothing in the image':<24} {tally.nothing_found:>4}")
    print(f"  {'could not be read':<24} {len(tally.unreadable):>4}")
    for run_id, reason in tally.unreadable:
        print(f"    {run_id}  {reason}")


def _print_verification(failures: list[str]) -> None:
    print("\nverification:")
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
        help="apply the values. Without it every batch runs and is then rolled back.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="stop after this many runs. Worth using for a first dry run: every image "
        "costs a Gemini call whether or not the result is kept.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"runs per transaction (default {BATCH_SIZE}). A crash loses at most one batch.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
