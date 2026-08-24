"""Clear the test runs, redemptions and ledger rows from the production database.

One-off, for launch day: the club has been trying the app out, and those trial runs and
redemptions must not become anyone's real 100 km total. Everything that describes *who
the club is* stays — members, campaigns, the four real rewards and their stock,
announcements, and every consent, screening, health record and audit row. The two
switched-off rewards left over from the same trial go with the rest of it.

Three things make this safe enough to point at production:

  - **It refuses to run against a host nobody named.** `--expect-host` has to match the
    host in DATABASE_URL, so aiming at the backup branch (which exists to restore from,
    not to delete from) or at a local database means passing the wrong host and being
    stopped before a single statement runs.
  - **It rolls back by default.** Without `--commit` the whole thing runs inside a
    transaction that is thrown away, which is what makes "show me what it would do" a
    real answer rather than a promise.
  - **It verifies before it commits.** Every table the brief says not to touch is counted
    before and after, and the reward stock is compared row by row. One failed check
    rolls the transaction back and raises.

Deletion order is forced by the schema, not by preference: `points_ledger` holds
RESTRICT foreign keys into `run_entry` and `redemption`, so the ledger goes first or
nothing goes at all. TRUNCATE ... CASCADE would satisfy the constraints by deleting
through them, which is exactly the wrong answer here — it would take members with it.

    python scripts/clear_test_data.py --expect-host ep-xxxx.neon.tech            # dry run
    python scripts/clear_test_data.py --expect-host ep-xxxx.neon.tech --commit

Uses the app's own settings, so it connects the way the API connects. It is deliberately
not async: the app has no async engine, this is four sequential statements, and a script
that runs on production should look like the code that has been tested against it.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from sqlalchemy import Connection, create_engine, make_url, text

from app.config import get_settings

# In dependency order: the ledger's RESTRICT keys point at the other two.
DELETE_ORDER = ("points_ledger", "redemption", "run_entry")

# Counted before and after and required to be identical. Not because anything here
# deletes from them, but because "nothing else moved" is the claim being made, and a
# claim that is checked is worth more than one that is intended.
UNTOUCHED = (
    "member",
    "campaign",
    "announcement",
    "consent",
    "screening",
    "health_record",
    "audit_log",
)

# Two rewards left over from trying the app out in August ("เสื้อ 2025", "อิอิ"), both
# already switched off so no member can see them. Deactivated is not the same thing as
# test data, so this does not lean on the flag alone: the count has to be exactly the two
# that were inspected, and the four survivors are checked stock by stock afterwards.
REWARD_CLEANUP = "DELETE FROM reward WHERE is_active = false"
EXPECTED_INACTIVE_REWARDS = 2

# What production is expected to hold once this has run. These are a fingerprint as much
# as a rule: a database with different rewards in it is not the database this script was
# written for, and the gate stops rather than guessing.
EXPECTED_CAMPAIGNS = 2
EXPECTED_REWARD_STOCK = (8, 11, 14, 23)  # sorted; the real values entered before launch


def main() -> int:
    args = _parse_args()
    url = make_url(get_settings().database_url)

    # No password, ever — not even on a terminal nobody else is reading.
    print(f"target   : {url.username}@{url.host}/{url.database}")
    print(f"expected : {args.expect_host}")
    if url.host != args.expect_host:
        print("\nREFUSED: DATABASE_URL points somewhere else. Nothing was run.")
        return 2
    print(f"mode     : {'COMMIT' if args.commit else 'dry run (rolls back)'}\n")

    engine = create_engine(url, pool_pre_ping=True, future=True)
    with engine.connect() as connection, connection.begin() as transaction:
        before = _snapshot(connection)
        _print_counts("before", before)

        deleted = {
            table: connection.execute(text(f"DELETE FROM {table}")).rowcount
            for table in DELETE_ORDER
        }
        # After the redemptions, whose reward_id is a RESTRICT key: a reward cannot go
        # while anything has redeemed it.
        deleted["reward (inactive)"] = connection.execute(text(REWARD_CLEANUP)).rowcount
        print("\ndeleted  : " + ", ".join(f"{t}={n}" for t, n in deleted.items()))

        after = _snapshot(connection)
        _print_counts("after", after)

        failures = _verify(before, after, deleted)
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


def _snapshot(connection: Connection) -> dict[str, Any]:
    counts: dict[str, Any] = {
        table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        for table in (*DELETE_ORDER, *UNTOUCHED)
    }
    # Per row, not just the total: a script that swapped two rewards' stock would leave
    # the sum untouched and the club short of shirts.
    rewards = connection.execute(text("SELECT id, stock, is_active FROM reward")).all()
    counts["reward"] = len(rewards)
    counts["reward_stock"] = {str(row.id): row.stock for row in rewards}
    counts["reward_inactive"] = sum(1 for row in rewards if not row.is_active)
    return counts


def _verify(
    before: dict[str, Any], after: dict[str, Any], deleted: dict[str, int]
) -> list[str]:
    failures = []

    for table in DELETE_ORDER:
        if after[table] != 0:
            failures.append(f"{table} should be empty, found {after[table]}")
        if deleted[table] != before[table]:
            # More rows deleted than were counted means something wrote to the table
            # while this was running, and the "before" numbers reported above are a lie.
            failures.append(
                f"{table}: deleted {deleted[table]} but counted {before[table]} beforehand"
            )

    for table in UNTOUCHED:
        if after[table] != before[table]:
            failures.append(f"{table} changed: {before[table]} -> {after[table]}")

    if after["campaign"] != EXPECTED_CAMPAIGNS:
        failures.append(f"campaign should be {EXPECTED_CAMPAIGNS}, found {after['campaign']}")

    # The reward cleanup, checked from both ends: exactly the two switched-off rows that
    # were inspected went, and every row still standing is one that was there before,
    # with the stock it had before.
    if before["reward_inactive"] != EXPECTED_INACTIVE_REWARDS:
        failures.append(
            f"expected {EXPECTED_INACTIVE_REWARDS} inactive rewards to remove, "
            f"found {before['reward_inactive']}"
        )
    if deleted["reward (inactive)"] != before["reward_inactive"]:
        failures.append(
            f"reward: deleted {deleted['reward (inactive)']} "
            f"but counted {before['reward_inactive']} inactive beforehand"
        )
    if after["reward_inactive"] != 0:
        failures.append(f"{after['reward_inactive']} inactive reward(s) still present")

    expected_rewards = len(EXPECTED_REWARD_STOCK)
    if after["reward"] != expected_rewards:
        failures.append(f"reward should be {expected_rewards} rows, found {after['reward']}")

    stock = tuple(sorted(after["reward_stock"].values()))
    if stock != EXPECTED_REWARD_STOCK:
        failures.append(f"reward stock should be {EXPECTED_REWARD_STOCK}, found {stock}")

    survivors = {
        reward_id: stock_
        for reward_id, stock_ in before["reward_stock"].items()
        if reward_id in after["reward_stock"]
    }
    if after["reward_stock"] != survivors:
        failures.append("a surviving reward's stock changed")

    return failures


def _print_counts(label: str, counts: dict[str, Any]) -> None:
    print(f"{label}:")
    for table in (*DELETE_ORDER, *UNTOUCHED):
        print(f"  {table:<16} {counts[table]:>4}")
    print(f"  {'reward':<16} {counts['reward']:>4}  ({counts['reward_inactive']} inactive)")
    print(f"  {'reward stock':<16} {sorted(counts['reward_stock'].values())}")


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
        help="apply the deletion. Without it everything runs and is then rolled back.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
