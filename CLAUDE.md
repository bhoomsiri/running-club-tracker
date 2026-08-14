# CLAUDE.md — Running Club App

Master context for this repository. Read this before touching any code.
For deeper how-to, consult the skills in `.claude/skills/` (see "Skills" at the bottom).

---

## What this project is

A full-stack web app for a running club (~100 members). Members submit their runs
with a photo as evidence; the app accumulates distance per person and runs yearly
activities ("campaigns"). This year has two campaigns: a 100 km cumulative challenge
and a run-to-earn-rewards program. It also stores basic health data (before/after an
activity), which is **sensitive personal data under Thailand's PDPA**.

Priorities, in order: **correct → secure → fast/stable → minimal code**. This is a
small app with sensitive data and one maintainer — favour boring, well-understood
patterns over clever ones. Do not add libraries or abstractions that aren't needed
for the current feature.

---

## Stack (do not swap without being asked)

| Layer          | Choice                                             |
|----------------|----------------------------------------------------|
| Frontend       | Next.js (App Router) + TypeScript + Tailwind       |
| Auth           | Clerk (`@clerk/nextjs` front). Back: JWT verified with **PyJWT + PyJWKClient** against Clerk's JWKS; webhooks verified with **svix** |
| Backend        | FastAPI (Python 3.12)                              |
| ORM / migrate  | SQLAlchemy 2.x + Alembic                           |
| DB driver      | psycopg (v3)                                       |
| Validation     | Pydantic v2 + pydantic-settings                    |
| Object storage | S3-compatible: Cloudflare R2 (prod) / MinIO (local) via boto3 |
| AI vision      | Gemini (`google-genai`) — screenshot → run data    |
| Test / lint    | pytest, ruff, mypy                                 |
| CI/CD          | GitHub Actions → Cloud Run + Vercel + Neon         |

Token verification sits behind the `TokenVerifier` port, so swapping in the
`clerk-backend-api` SDK later means changing one adapter. PyJWT is the current choice
because it lets the tests prove golden rule #2 against **real signatures** — a forged
key, `alg=none`, an expired token, the wrong issuer — where the SDK would have to be
mocked, testing nothing.

---

## Golden rules (never violate)

These are the invariants that keep the app correct, secure, and lawful. If a change
would break one of these, stop and flag it instead of proceeding.

1. **`domain/` and `application/` never import framework code.** No `fastapi`,
   no `sqlalchemy`, no `boto3`, no `google.genai` in those two folders. They depend
   only on the standard library and on each other. This is the core of the
   architecture — see the backend skill. Verify with:
   `grep -rn "import fastapi\|import sqlalchemy\|import boto3" app/domain app/application`
   → must be empty.

2. **`member_id` always comes from the verified token, never from the request body.**
   Every read/write is scoped to the caller's own `member_id`. This is the single
   defence against a member reading or writing another member's data (IDOR).

3. **AI only pre-fills; the human confirms.** The Gemini extractor produces a *draft*.
   Never auto-commit AI-read values. The confirmed value the user submits is the source
   of truth. If the model can't read a field, it returns `null` + a warning — it never
   guesses a number.

4. **Never fabricate data.** Anywhere a value is unknown, represent it as `null`/absent
   and flag it. Do not invent distances, dates, or figures to fill a gap.

5. **Points are a ledger, not a column.** A member's balance is `SUM(delta)` over
   `points_ledger`. Redemption happens inside one DB transaction (lock → check balance →
   insert redemption + negative ledger row → decrement stock → commit) so concurrent
   redeems can't double-spend. Two locking rules make that hold, and **any** future use
   case that writes a ledger row (superuser `adjustment`, a reject-driven `reversal`,
   crediting a run) must follow both:

   - **Always take the account lock first.** Call
     `ledger.serialize_account(member_id, campaign_id)` inside the transaction, before
     reading the balance. It is an app-level mutex keyed on the account, so it only
     prevents double-spending while *every* writer takes it — one path that skips it
     walks straight around the lock. A row lock cannot replace it: the balance is a SUM
     over rows that don't exist yet, so two transactions each INSERT their own new row.
   - **Always lock in the same order: reward row → account.** `redeem_reward` takes
     `rewards.get_for_update()` and then `serialize_account()`. A use case that grabs
     these two in the opposite order can deadlock against it.

6. **Money-like and reward-affecting numbers use `numeric`, never `float`.** Distance,
   points, costs. Float rounding silently corrupts rewards.

7. **Health data is gated by consent and access-logged.** Never write a `health_record`
   without an active `consent(purpose='health_data')`. Never let anyone but the owner or
   an authorised admin read it, and write an `audit_log` row on every admin access.

8. **Never log sensitive data.** No tokens, no health values, no email in logs. Log
   `member_id` + action only.

---

## Architecture — hexagonal (ports & adapters)

Dependency arrows point **inward**. Outer layers know about inner layers, never the
reverse:

```
api  →  adapters  →  application  →  domain
                                       ↑
                    everything depends on domain; domain depends on nobody
```

| Layer         | Contains                          | May import                         |
|---------------|-----------------------------------|------------------------------------|
| `domain`      | entities + business rules         | stdlib only                        |
| `application` | ports (Protocol) + use cases      | `domain` + stdlib                  |
| `adapters`    | DB / Clerk / storage / AI impls   | anything (this is where frameworks live) |
| `api`         | FastAPI routers, DTOs, wiring     | `application`, `adapters`, framework |

Why: use cases depend on **interfaces** (`Protocol`), so implementations swap freely —
real SQLAlchemy repo in prod, in-memory fake in tests, MinIO locally / R2 in prod —
without the business logic knowing. That is what makes this testable and stable.

---

## Repository structure

```
running-club/
├── CLAUDE.md
├── .claude/skills/            # club-backend / club-frontend / security-pdpa
├── docker-compose.yml         # local: postgres + minio (+ optional api/web)
├── .github/workflows/         # ci.yml (test gate), deploy.yml
│
├── backend/
│   └── app/
│       ├── domain/            # entities.py, campaign.py, redemption.py,
│       │   │                  # campaigns/ (policy registry), errors.py
│       ├── application/
│       │   ├── ports/         # *_repository.py, image_storage.py,
│       │   │                  # run_extractor.py, unit_of_work.py, clock.py
│       │   └── use_cases/     # one file = one action
│       ├── adapters/
│       │   ├── persistence/   # models.py, mappers.py, sqlalchemy_*_repository.py, uow
│       │   ├── auth/          # clerk_authenticator.py, clerk_webhook.py
│       │   ├── storage/       # s3_image_storage.py (R2 + MinIO, same code)
│       │   └── extraction/    # gemini_extractor.py
│       ├── api/               # deps.py, schemas.py, errors.py, routers/
│       ├── config.py, db.py, main.py
│       ├── alembic/           # migrations
│       └── tests/             # fakes/, domain/, application/, api/
│
└── frontend/
    └── src/
        ├── app/               # App Router: dashboard, submit, campaigns,
        │                      # rewards, leaderboard, sign-in, sign-up
        ├── components/
        ├── lib/               # api.ts (useApi + Bearer token), types.ts
        └── middleware.ts      # clerkMiddleware + route protection
```

---

## Conventions

- **One use case = one file = one class with one `execute()`** (SRP). Adding a feature
  means adding a use case, not editing an existing one (OCP).
- **Campaign types are data + strategy, not `if/elif`.** New activity format = new
  `CampaignPolicy` file + one registry line. Never branch on `campaign.type` outside
  the policy registry. Check: `grep -rn "campaign.type ==" app/application app/api` → empty.
- **Domain entities are frozen dataclasses**; validation lives in the entity's factory
  (`create()`), so every path that builds one is validated in one place.
- **DTOs (Pydantic) live in `api/schemas.py`** and are separate from domain entities.
  `adapters/persistence/mappers.py` converts ORM ↔ domain so the domain stays clean.
- **Config via `pydantic-settings`** reading env; never hardcode secrets. `.env` is
  gitignored; `.env.example` is committed.
- **Migrations are explicit** — a separate CI step (`alembic upgrade head`), never
  auto-run on app startup (multiple instances would race).
- **Never edit a migration that has been applied to a real database.** Once production
  exists, every schema change is a NEW migration (`0002`, `0003`, …). Editing an applied
  one in place is silent drift: `alembic upgrade head` is a no-op for a database already
  at that revision, so the change reaches your fresh local DB and never reaches prod.
  (Pre-launch, editing `0001` in place was fine — that ends the day the prod DB is created.)
- **Timestamps `timestamptz`; the clock is a `Clock` port**, so time is injectable and
  tests are deterministic (never call `datetime.now()` inside a use case).

---

## Testing (this is a requirement, not an afterthought)

The architecture exists partly to make tests fast and meaningful:

- **Unit-test use cases against fake repositories** (in `tests/fakes/`) — no DB, no
  network. A `FixedClock` makes time deterministic. This is the LSP payoff: the same
  use case runs on a fake in tests and SQLAlchemy in prod.
- **Test each `CampaignPolicy` in isolation** — pure functions, trivial to test.
- **The two must-cover cases**: (a) `redeem_reward` cannot double-spend or go negative;
  (b) writing health data without active consent is rejected. These protect money and PDPA.
- **CI runs `ruff`, `mypy app tests`, `pytest` as a gate** — no deploy if they fail.
  `mypy` also catches accidental architecture violations (a use case depending on a
  concrete class). Type-check `tests` too, not just `app`: the fakes are what prove a
  use case still works against any implementation, so an LSP break between a fake and
  the real SQLAlchemy repository only shows up if the fakes are checked.

---

## Security & PDPA

Eight items must be baked into the relevant code as it's written, not bolted on later.
Full detail + code sketches are in `.claude/skills/security-pdpa`. Summary:

1. Verify Clerk **webhook signatures** with `svix` — reject unsigned/invalid.
2. **Admin role** gates health-data access; write `audit_log` on every access.
3. **Filter uploads**: check magic bytes (not just extension), enforce a size cap,
   whitelist jpeg/png/webp, keep the bucket **private**, serve via short-lived
   presigned URLs.
4. **Strip EXIF** from images (screenshots carry GPS/time → location leak).
5. **CORS locked** to the frontend domain — never `*`.
6. **Rate-limit** the API, especially `/runs/extract` (each call costs Gemini money).
7. **`pip-audit` + Dependabot** in CI for dependency CVEs.
8. **Never log** tokens, health values, or email.

Highest-stakes for this app: #1, #2, #8 — they touch health data directly, so a miss is
a PDPA breach, not just a bug.

---

## Common commands

```bash
# Local dev
docker compose up -d                 # postgres + minio
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev

# Backend quality gate (run before commit)
cd backend
ruff check . && mypy app tests && pytest

# Migrations
alembic revision --autogenerate -m "message"
alembic upgrade head
```

---

## Skills — when to reach for which

- **`.claude/skills/club-backend`** — adding/changing any FastAPI feature: entities, ports,
  use cases, adapters, routers, the campaign strategy, the redemption transaction, and
  how to test all of it. Consult it whenever working under `backend/`.
- **`.claude/skills/club-frontend`** — any Next.js work: pages, components, the Clerk auth
  wiring, the token-attached API client, and the evidence→extract→confirm submit flow.
- **`.claude/skills/security-pdpa`** — any work that touches uploads, health data,
  webhooks, CORS, rate limiting, logging, or deployment. Cross-cutting; consult it
  alongside the backend skill whenever a change is near sensitive data.

Work in small, reviewable steps. Suggested build order:
schema + migration → redeem_reward + ledger → consent-gate + admin + audit →
evidence + Gemini extract flow → frontend pages.
