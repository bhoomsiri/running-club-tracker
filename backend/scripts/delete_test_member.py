"""Hard-delete the one test member from the production database.

The account used to try the app out before launch. Deleting it is also the first real
exercise of the erasure path PDPA requires, so it deletes the way the erasure use case
will have to: explicitly, in dependency order, inside one transaction. The order is the
one recorded at the top of `models.py` and it is not a preference — `points_ledger`
holds ON DELETE RESTRICT keys into `run_entry` and `redemption`, which collide with the
CASCADE from `member`, so a single cascade from `member` cannot unwind it.

Guards, same shape as clear_test_data.py:

  - **`--expect-host`** must match the host in DATABASE_URL, so the backup branch cannot
    be hit by accident.
  - **`--expect-name`** must match the display name of the row about to go. The operator
    has to say who they mean; a typo refuses rather than deletes.
  - **The superuser is identified by clerk_user_id, not by role**, and the script refuses
    if the target carries that id — a role column can be edited, that id cannot be
    anything but the account it belongs to.
  - **Dry run by default.** Without `--commit` everything runs and is rolled back.

    python scripts/delete_test_member.py --expect-host ep-xxxx.neon.tech \
        --expect-name "BRIGHT"            # dry run
    python scripts/delete_test_member.py --expect-host ep-xxxx.neon.tech \
        --expect-name "BRIGHT" --commit

One thing this cannot delete, by design: audit rows written *about* the member by an
admin. `audit_log.subject_member_id` is ON DELETE SET NULL, so those rows survive with
the subject blanked — the record that a health record was read has to outlive the health
record, or the accountability the log exists for goes with it. Rows the member wrote
themselves (`actor_member_id`) are deleted, because RESTRICT would otherwise block the
whole thing. Neither applies to the account this was written for, which has no audit
rows at all, but the erasure use case will meet both.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Any

from sqlalchemy import Connection, create_engine, make_url, text

from app.config import get_settings

# The account this script must never touch, pinned by the id Clerk issued it. Checked
# against the target as well as counted afterwards.
SUPERUSER_CLERK_USER_ID = "user_3IMXUUA3dhZGmPcQRAjIxRJXZ1L"

# In dependency order, every statement scoped to the one member. The ledger's RESTRICT
# keys force the first three; audit_log's RESTRICT on actor_member_id forces the fourth
# to come before `member`.
DELETE_ORDER = (
    ("points_ledger", "DELETE FROM points_ledger WHERE member_id = :target"),
    ("redemption", "DELETE FROM redemption WHERE member_id = :target"),
    ("run_entry", "DELETE FROM run_entry WHERE member_id = :target"),
    ("audit_log (as actor)", "DELETE FROM audit_log WHERE actor_member_id = :target"),
    ("health_record", "DELETE FROM health_record WHERE member_id = :target"),
    ("consent", "DELETE FROM consent WHERE member_id = :target"),
    ("screening", "DELETE FROM screening WHERE member_id = :target"),
    ("member", "DELETE FROM member WHERE id = :target"),
)

# Sensitive tables, counted per member so "the superuser's rows did not move" is a
# checked fact rather than an assumption.
SCOPED = ("points_ledger", "redemption", "run_entry", "health_record", "consent", "screening")


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
        superuser, target, refusal = _identify(connection, args.expect_name)
        if refusal is not None:
            transaction.rollback()
            print(f"\nREFUSED: {refusal}\nNothing was deleted.")
            return 2

        assert superuser is not None and target is not None  # narrowed by `refusal`
        print(f"superuser: {superuser.display_name!r}  {superuser.clerk_user_id}  (keep)")
        print(f"to delete: {target.display_name!r}  {target.clerk_user_id}  role={target.role}\n")

        before = _snapshot(connection, superuser.id, target.id)
        _print_counts("before", before)

        deleted = {
            label: connection.execute(text(sql), {"target": target.id}).rowcount
            for label, sql in DELETE_ORDER
        }
        print("\ndeleted  : " + ", ".join(f"{label}={n}" for label, n in deleted.items()))

        after = _snapshot(connection, superuser.id, target.id)
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


def _identify(connection: Connection, expect_name: str) -> tuple[Any, Any, str | None]:
    """The superuser and the single member to delete, or a reason to refuse.

    Deliberately picky. Everything downstream is scoped to one id, so if that id is wrong
    nothing else in this file can save it.
    """
    rows = connection.execute(
        text("SELECT id, role, display_name, clerk_user_id FROM member ORDER BY created_at")
    ).all()

    superusers = [row for row in rows if row.clerk_user_id == SUPERUSER_CLERK_USER_ID]
    if len(superusers) != 1:
        return None, None, f"expected exactly 1 superuser by clerk id, found {len(superusers)}"
    superuser = superusers[0]
    if superuser.role != "superuser":
        return None, None, f"the pinned account has role {superuser.role!r}, not 'superuser'"

    others = [row for row in rows if row.clerk_user_id != SUPERUSER_CLERK_USER_ID]
    if len(others) != 1:
        return None, None, f"expected exactly 1 member besides the superuser, found {len(others)}"
    target = others[0]

    if target.role == "superuser":
        return None, None, "the target holds the superuser role; refusing"
    if target.clerk_user_id == SUPERUSER_CLERK_USER_ID:
        return None, None, "the target carries the superuser's clerk id; refusing"
    if target.display_name != expect_name:
        return (
            None,
            None,
            f"the member to delete is {target.display_name!r}, not {expect_name!r} "
            f"(pass --expect-name with the name you mean)",
        )
    return superuser, target, None


def _snapshot(
    connection: Connection, superuser_id: uuid.UUID, target_id: uuid.UUID
) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "member": connection.execute(text("SELECT count(*) FROM member")).scalar_one(),
        "superuser": connection.execute(
            text("SELECT count(*) FROM member WHERE role = 'superuser'")
        ).scalar_one(),
        "superuser_present": connection.execute(
            text("SELECT count(*) FROM member WHERE clerk_user_id = :cid"),
            {"cid": SUPERUSER_CLERK_USER_ID},
        ).scalar_one(),
        "audit_log": connection.execute(text("SELECT count(*) FROM audit_log")).scalar_one(),
        "audit_as_actor": connection.execute(
            text("SELECT count(*) FROM audit_log WHERE actor_member_id = :t"), {"t": target_id}
        ).scalar_one(),
        "audit_as_subject": connection.execute(
            text("SELECT count(*) FROM audit_log WHERE subject_member_id = :t"), {"t": target_id}
        ).scalar_one(),
    }
    for table in SCOPED:
        for label, member_id in (("superuser", superuser_id), ("target", target_id)):
            counts[f"{table}:{label}"] = connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE member_id = :m"), {"m": member_id}
            ).scalar_one()
    return counts


def _verify(
    before: dict[str, Any], after: dict[str, Any], deleted: dict[str, int]
) -> list[str]:
    failures = []

    if deleted["member"] != 1:
        failures.append(f"expected to delete exactly 1 member, deleted {deleted['member']}")
    if after["member"] != before["member"] - 1:
        failures.append(f"member should be {before['member'] - 1}, found {after['member']}")

    # The survivor has to be the superuser — not merely "a superuser row exists".
    if after["superuser"] != 1:
        failures.append(f"superuser count should be 1, found {after['superuser']}")
    if after["superuser_present"] != 1:
        failures.append("the pinned superuser clerk id is no longer in the member table")
    if after["member"] != 1:
        failures.append(f"exactly the superuser should remain, found {after['member']} rows")

    # Nothing of the superuser's moved.
    for table in SCOPED:
        key = f"{table}:superuser"
        if after[key] != before[key]:
            failures.append(f"{table} for the superuser changed: {before[key]} -> {after[key]}")

    # Nothing of the target's is left behind.
    for table in SCOPED:
        key = f"{table}:target"
        if after[key] != 0:
            failures.append(f"{table} still holds {after[key]} row(s) for the deleted member")

    # The audit trail: rows the member wrote go, rows written about them survive with the
    # subject blanked by ON DELETE SET NULL. Either way nothing may still point at the id.
    if deleted["audit_log (as actor)"] != before["audit_as_actor"]:
        failures.append(
            f"audit_log: deleted {deleted['audit_log (as actor)']} as actor "
            f"but counted {before['audit_as_actor']} beforehand"
        )
    if after["audit_log"] != before["audit_log"] - before["audit_as_actor"]:
        expected = before["audit_log"] - before["audit_as_actor"]
        failures.append(f"audit_log should be {expected}, found {after['audit_log']}")
    if after["audit_as_actor"] or after["audit_as_subject"]:
        failures.append("audit_log still references the deleted member")

    return failures


def _print_counts(label: str, counts: dict[str, Any]) -> None:
    print(f"{label}:")
    print(f"  {'member':<22} {counts['member']:>4}  ({counts['superuser']} superuser)")
    print(
        f"  {'audit_log':<22} {counts['audit_log']:>4}"
        f"  (target: actor={counts['audit_as_actor']} subject={counts['audit_as_subject']})"
    )
    for table in SCOPED:
        superuser = counts[f"{table}:superuser"]
        target = counts[f"{table}:target"]
        print(f"  {table:<22} {'':>4}  superuser={superuser}  target={target}")


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
        "--expect-name",
        required=True,
        help="display name of the member to delete; refuses if the row does not match",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="apply the deletion. Without it everything runs and is then rolled back.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
