"""Fetch the picture Clerk already holds for members who joined before the app stored it.

`member.image_url` / `member.has_image` arrived in migration 0010 and are written only by
the verified `user.created` / `user.updated` webhook. Everyone who signed up before that
has NULL and false, and nothing will change it until they happen to edit their Clerk
profile — so this asks Clerk once for each of them.

After this runs, nothing else here does: ongoing changes keep arriving by webhook exactly
as they do now. This is a one-off to fill in the past, not a second sync path.

Same rules as the webhook, deliberately:

  - **`has_image` is `is True`, never truthy.** An answer we could not read must not
    become "yes, that is their photo".
  - **`image_url` is stored only when `has_image` is true.** Clerk gives every account a
    URL and points it at a generated default for anyone who never set a picture; storing
    that would put a stranger's styling on a member who chose nothing, which is the whole
    reason 0010 is two columns instead of one.

Narrow on purpose:

  - **only `image_url` and `has_image` are written.** Not the display name — that one the
    member owns and the webhook may only set on INSERT — and nothing else on the row.
  - every member is asked about, and only rows whose answer differs are updated, so
    running it twice writes nothing the second time.
  - a member Clerk no longer knows is counted and left exactly as they are.

The key is read for the length of one run and is never added to `Settings`. The running
service authenticates members against Clerk's JWKS and verifies webhooks with svix;
neither needs a Backend API key, and a key that can read every user in the instance has
no business sitting in the config of a service that does not use it.

It is taken from the environment or from `backend/.env`, whichever has it — the same file
`Settings` reads DATABASE_URL out of, so both live in one place.

    python scripts/backfill_avatars.py --expect-host ep-xxxx.neon.tech
    python scripts/backfill_avatars.py --expect-host ep-xxxx.neon.tech --commit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, NamedTuple

from dotenv import load_dotenv
from sqlalchemy import Connection, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from app.config import get_settings

CLERK_API = "https://api.clerk.com/v1/users"
# Not optional. api.clerk.com sits behind Cloudflare, which refuses the default
# `Python-urllib/3.x` outright — every request comes back 403 with Cloudflare's error
# 1010 and never reaches Clerk, whatever the key is. Naming the client fixes it.
USER_AGENT = "ptrh-runclub-backfill/1.0"
# Clerk's published limit is far above this; ~40 members at 7/second is nowhere near it
# and costs twelve seconds in total. Being a polite client is cheaper than being retried.
PAUSE_SECONDS = 0.15
REQUEST_TIMEOUT_SECONDS = 15
# Only a 429 or a 5xx is worth asking again — a 404 will be a 404 next time too.
RETRY_BACKOFF_SECONDS = (1.0, 3.0)


class Avatar(NamedTuple):
    image_url: str | None
    has_image: bool


class Row(NamedTuple):
    id: uuid.UUID
    clerk_user_id: str
    current: Avatar


def main() -> int:
    args = _parse_args()

    # pydantic-settings reads .env into `Settings` and not into the process environment,
    # so a key sitting beside DATABASE_URL in that file would be invisible here. Loading
    # it explicitly means both live in one place; an exported variable still wins, which
    # is what `override=False` is for.
    load_dotenv(override=False)

    key = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not key:
        print(
            "REFUSED: CLERK_SECRET_KEY is not set — not in the environment and not in"
            " backend/.env. Nothing was run."
        )
        return 2

    url = make_url(get_settings().database_url)

    # No password, ever — not even on a terminal nobody else is reading. The Clerk key is
    # never printed at all, not even a prefix of it.
    print(f"target   : {url.username}@{url.host}/{url.database}")
    print(f"expected : {args.expect_host}")
    if url.host != args.expect_host:
        print("\nREFUSED: DATABASE_URL points somewhere else. Nothing was run.")
        return 2
    print(f"mode     : {'COMMIT' if args.commit else 'dry run (rolls back)'}")
    print(f"clerk    : key loaded from CLERK_SECRET_KEY ({len(key)} chars)\n")

    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        connection = engine.connect()
    except OperationalError as error:
        # A wrong password buries one useful line under sixty of driver stack. The
        # message is the server's own and carries no credential — psycopg reports the
        # user it was refused for, which is the thing worth seeing.
        print(f"\nCould not connect: {_first_line(error)}")
        print("Check DATABASE_URL in backend/.env — user, password and database name.")
        return 2

    with connection, connection.begin() as transaction:
        before = _avatars(connection)
        rows = _members(connection)
        print(f"members  : {len(rows)} to ask Clerk about\n")

        fetched: dict[uuid.UUID, Avatar] = {}
        missing: list[uuid.UUID] = []
        failed: list[tuple[uuid.UUID, str]] = []

        for index, row in enumerate(rows, start=1):
            try:
                avatar = _fetch(row.clerk_user_id, key)
            except NotFoundAtClerk:
                missing.append(row.id)
            except ClerkError as error:
                # Recorded and reported, never fatal: one unreachable account should not
                # cost the other thirty-nine their picture.
                failed.append((row.id, str(error)))
            else:
                fetched[row.id] = avatar
            _progress(index, len(rows))
            time.sleep(PAUSE_SECONDS)

        changed = {
            member_id: avatar
            for member_id, avatar in fetched.items()
            if avatar != _by_id(rows)[member_id].current
        }
        _print_findings(rows, fetched, changed, missing, failed)

        updated = 0
        for member_id, avatar in changed.items():
            updated += connection.execute(
                text(
                    "UPDATE member SET image_url = :url, has_image = :has"
                    " WHERE id = :id AND deleted_at IS NULL"
                ),
                {"url": avatar.image_url, "has": avatar.has_image, "id": member_id},
            ).rowcount
        print(f"\nupdated  : {updated} member row(s)")

        after = _avatars(connection)
        failures = _verify(before, after, changed, updated)
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


def _reason(error: urllib.error.HTTPError) -> str:
    """What the responder said, in one short line.

    Clerk answers with `{"errors": [{"code", "message"}]}`; Cloudflare, when it refuses
    the request before Clerk sees it, answers with an RFC-7807 `title`. Falling back to
    the raw start of the body covers anything else.
    """
    try:
        body = error.read()[:400].decode("utf-8", "replace")
    except Exception:
        return "no body"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:120] or "no body"
    if isinstance(parsed, dict):
        errors = parsed.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            return str(errors[0].get("message") or errors[0].get("code") or body)[:120]
        if parsed.get("title"):
            return str(parsed["title"])[:120]
    return body.strip()[:120]


def _first_line(error: Exception) -> str:
    """Postgres puts the reason on line one and its connection attempts on the rest."""
    return str(error).strip().splitlines()[0]


class VerificationFailed(RuntimeError):
    pass


class ClerkError(RuntimeError):
    pass


class NotFoundAtClerk(ClerkError):
    pass


def _fetch(clerk_user_id: str, key: str) -> Avatar:
    """One account's picture, by the same two rules the webhook applies."""
    data = _get(f"{CLERK_API}/{clerk_user_id}", key)
    has_image = data.get("has_image") is True
    raw = data.get("image_url")
    url = raw.strip() if isinstance(raw, str) and raw.strip() else None
    # The URL is kept only when Clerk says the member set a picture; otherwise it points
    # at a generated default and the app draws its own initials instead.
    return Avatar(image_url=url if has_image else None, has_image=has_image)


def _get(endpoint: str, key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    for attempt in range(len(RETRY_BACKOFF_SECONDS) + 1):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode("utf-8"))
                if not isinstance(body, dict):
                    raise ClerkError("unexpected response shape")
                return body
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise NotFoundAtClerk("no such user at Clerk") from error
            transient = error.code == 429 or error.code >= 500
            if not transient or attempt == len(RETRY_BACKOFF_SECONDS):
                # The status and whatever the body says went wrong. A response body
                # carries no request header, so nothing here can leak the key — and
                # reporting the status alone once hid a Cloudflare block behind forty
                # identical "HTTP 403" lines that looked like a bad key.
                raise ClerkError(f"HTTP {error.code}: {_reason(error)}") from error
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])
        except urllib.error.URLError as error:
            if attempt == len(RETRY_BACKOFF_SECONDS):
                raise ClerkError(f"network error: {error.reason}") from error
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])
    raise ClerkError("exhausted retries")


def _members(connection: Connection) -> list[Row]:
    """Every live member, not only the ones with nothing stored.

    Asking about all of them is what makes this idempotent and self-correcting: someone
    who changed their picture before the webhook existed is fixed too, and a second run
    finds every answer already matching and writes nothing. At this club's size that is
    forty requests either way.
    """
    rows = connection.execute(
        text(
            "SELECT id, clerk_user_id, image_url, has_image FROM member"
            " WHERE deleted_at IS NULL ORDER BY created_at"
        )
    ).all()
    return [
        Row(row.id, row.clerk_user_id, Avatar(row.image_url, row.has_image)) for row in rows
    ]


def _by_id(rows: list[Row]) -> dict[uuid.UUID, Row]:
    return {row.id: row for row in rows}


def _avatars(connection: Connection) -> dict[str, Avatar]:
    """Every member's two columns, so "nothing else moved" is checked per row. Totals
    alone would hide two members swapping pictures."""
    return {
        str(row.id): Avatar(row.image_url, row.has_image)
        for row in connection.execute(
            text("SELECT id, image_url, has_image FROM member")
        ).all()
    }


def _verify(
    before: dict[str, Avatar],
    after: dict[str, Avatar],
    changed: dict[uuid.UUID, Avatar],
    updated: int,
) -> list[str]:
    failures = []

    if updated != len(changed):
        failures.append(f"{len(changed)} row(s) differed but {updated} were updated")
    if set(after) != set(before):
        failures.append("the set of members changed while the script was running")

    expected = {str(member_id) for member_id in changed}
    for member_id, was in before.items():
        now = after.get(member_id)
        if now is None or now == was:
            continue
        if member_id not in expected:
            failures.append(f"member {member_id} changed but was not one of the differences")
        elif now != changed[uuid.UUID(member_id)]:
            failures.append(f"member {member_id} did not end up holding what Clerk returned")

    for member_id in expected:
        if after.get(member_id) == before.get(member_id):
            failures.append(f"member {member_id} differed from Clerk but was not updated")

    # The rule the whole table has to keep: no URL is stored for anyone Clerk says has no
    # picture of their own.
    for member_id, avatar in after.items():
        if not avatar.has_image and avatar.image_url is not None:
            failures.append(f"member {member_id} has has_image=false but a stored URL")

    return failures


def _print_findings(
    rows: list[Row],
    fetched: dict[uuid.UUID, Avatar],
    changed: dict[uuid.UUID, Avatar],
    missing: list[uuid.UUID],
    failed: list[tuple[uuid.UUID, str]],
) -> None:
    with_picture = sum(1 for avatar in fetched.values() if avatar.has_image)
    print("\n\nfrom Clerk:")
    print(f"  {'asked':<22} {len(rows):>4}")
    print(f"  {'answered':<22} {len(fetched):>4}")
    print(f"  {'has a picture':<22} {with_picture:>4}")
    print(f"  {'default only':<22} {len(fetched) - with_picture:>4}")
    print(f"  {'not found at Clerk':<22} {len(missing):>4}")
    print(f"  {'could not be read':<22} {len(failed):>4}")

    # No URLs printed: the report is about how many, not about who looks like what.
    if changed:
        print(f"\nwould change {len(changed)} row(s):")
        for member_id, avatar in changed.items():
            print(f"  {member_id}  has_image -> {str(avatar.has_image).lower()}")
    else:
        print("\nnothing to change: every row already matches Clerk")

    for member_id, reason in failed:
        print(f"  FAILED  {member_id}  {reason}")


def _progress(done: int, total: int) -> None:
    # One line, rewritten, so ~40 requests do not fill the terminal.
    print(f"\rasking Clerk: {done}/{total}", end="", flush=True)


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
        help="apply the pictures. Without it everything runs and is then rolled back.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
