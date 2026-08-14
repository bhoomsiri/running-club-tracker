---
name: club-backend
description: How to build and change the FastAPI backend of THIS running-club app the hexagonal / ports-and-adapters way, following SOLID. (This is the running-club backend — not the Safem0de-GPT / RAG chatbot backend; this app uses Clerk auth and has campaigns/ledger/health, no retrieval pipeline.) Use this skill whenever working under backend/ — adding or editing an entity, a port, a use case, a repository or other adapter, a router or DTO, the campaign strategy/registry, the points-ledger redemption transaction, or the tests for any of these. Consult it even when the request sounds simple ("add an endpoint", "store the run", "let admins see X"), because the layering, the import boundaries, the ledger-transaction rule, and the fake-repository test pattern are easy to get subtly wrong. Read CLAUDE.md first for the golden rules; read the security-pdpa skill alongside this whenever the change is near uploads, health data, or webhooks.
---

# Backend — FastAPI, hexagonal, SOLID

The backend is layered so business logic never touches frameworks. Get the layering
right and everything else (testing, swapping storage, adding activities) falls out for
free. Get it wrong and you lose all of that. This skill is the how-to; CLAUDE.md holds
the non-negotiable rules.

## The one rule that governs everything

Dependencies point inward: `api → adapters → application → domain`.

- `domain/` imports **stdlib only**.
- `application/` imports `domain` + stdlib — never `fastapi`, `sqlalchemy`, `boto3`, `google.genai`.
- `adapters/` and `api/` are where all framework code lives.

Before finishing any backend change, run:
```bash
grep -rn "import fastapi\|import sqlalchemy\|import boto3\|import google" app/domain app/application
```
It must print nothing. If it doesn't, the abstraction leaked — fix it before moving on.

## How to add a feature (always this order)

Work inside-out. Each step depends only on the ones before it.

1. **Domain** — if the feature needs a new concept or rule, add/extend a frozen
   dataclass entity in `domain/`. Put validation in a `create()` classmethod so every
   construction path is validated once.
2. **Port** — if the use case needs something from the outside world (DB, storage, AI,
   time), define or extend a `Protocol` in `application/ports/`. Keep ports small and
   focused (ISP) — separate `RunRepository`, `Clock`, `ImageStorage` rather than one
   god-interface.
3. **Use case** — add one file in `application/use_cases/` with one class and one
   `execute()`. It takes ports in its constructor and depends only on those abstractions
   (DIP). It contains the orchestration; the rules live in the entity.
4. **Adapter** — implement the port for real in `adapters/` (SQLAlchemy repo, S3
   storage, Gemini extractor). This is the only place that imports frameworks.
5. **Wire** — in `api/deps.py`, add a `Depends` provider that constructs the use case
   with its concrete adapters. This is the single place implementations are chosen.
6. **Router** — in `api/routers/`, add a thin endpoint: parse the request DTO, pull
   `member_id` from the token dependency, call `use_case.execute(...)`, map domain
   errors to HTTP status, return a response DTO. No business logic in the router.
7. **Test** — unit-test the use case against a fake repository (see Testing below).

Adding a feature should mean **adding files, not editing existing use cases** (OCP).

## Ports are `Protocol`, not ABC

```python
# application/ports/run_repository.py
from typing import Protocol
from app.domain.entities import RunEntry

class RunRepository(Protocol):
    def add(self, run: RunEntry) -> None: ...
    def list_by_member(self, member_id: str) -> list[RunEntry]: ...
    def list_by_member_in_window(self, member_id: str, start, end) -> list[RunEntry]: ...
```

Structural typing means the SQLAlchemy adapter and the fake both satisfy this without
importing or inheriting from it — lowest possible coupling.

## Use case shape

```python
# application/use_cases/submit_run.py
from dataclasses import dataclass
from datetime import date
from app.domain.entities import RunEntry, RunSource
from app.application.ports.run_repository import RunRepository
from app.application.ports.clock import Clock

@dataclass
class SubmitRunCommand:
    member_id: str
    distance_km: float
    duration_seconds: int
    run_date: date
    evidence_key: str
    source: RunSource

class SubmitRun:
    def __init__(self, runs: RunRepository, clock: Clock):
        self._runs = runs
        self._clock = clock

    def execute(self, cmd: SubmitRunCommand) -> RunEntry:
        run = RunEntry.create(
            member_id=cmd.member_id, distance_km=cmd.distance_km,
            duration_seconds=cmd.duration_seconds, run_date=cmd.run_date,
            evidence_key=cmd.evidence_key, source=cmd.source,
            now=self._clock.now(),
        )
        self._runs.add(run)
        return run
```

`member_id` arrives in the command from the token dependency — never from the HTTP body.

## Router shape (thin)

```python
# api/routers/runs.py
@router.post("", response_model=RunResponse, status_code=201)
def submit_run(
    body: SubmitRunRequest,
    member_id: str = Depends(get_current_member_id),   # from verified token
    uc: SubmitRun = Depends(get_submit_run),
):
    try:
        run = uc.execute(SubmitRunCommand(member_id=member_id, **body.model_dump()))
    except InvalidRunError as e:
        raise HTTPException(422, str(e))
    return RunResponse.from_entity(run)
```

## Adding a new campaign type (the OCP showcase)

Activity formats change every year. They vary in two things only: what one run
contributes, and how contributions roll up into progress. Both are captured by a
`CampaignPolicy`. To add a format:

1. Add a value to `CampaignType` in `domain/campaign.py`.
2. Add a policy file in `domain/campaigns/` implementing `contribution()` and
   `progress()`.
3. Register it in `domain/campaigns/__init__.py` (one line in `_REGISTRY`).

Nothing else changes. Never write `if campaign.type == ...` outside the registry —
that branching is exactly what the registry exists to eliminate. Check:
```bash
grep -rn "campaign.type ==" app/application app/api   # must be empty
```

```python
# domain/campaigns/__init__.py
_REGISTRY = {
    CampaignType.CUMULATIVE_DISTANCE: CumulativeDistancePolicy(),
    CampaignType.REDEEM_REWARD: RedeemRewardPolicy(),
    # next year: CampaignType.STREAK: StreakPolicy(),
}

def policy_for(t: CampaignType) -> CampaignPolicy:
    try:
        return _REGISTRY[t]
    except KeyError as e:
        raise UnknownCampaignType(str(t)) from e
```

Progress is **derived from runs at read time** (filter runs into the campaign's date
window, run them through the policy). There is no stored progress table to fall out of
sync — runs are the single source of truth.

## The redemption transaction (get this exactly right)

Redeeming a reward touches money-like state and must be atomic, or concurrent taps
double-spend. Do it through a `UnitOfWork` in one transaction:

```python
# application/use_cases/redeem_reward.py
class RedeemReward:
    def __init__(self, uow: UnitOfWork):
        self._uow = uow

    def execute(self, member_id: str, reward_id) -> Redemption:
        with self._uow:                                  # begins a transaction
            reward = self._uow.rewards.get_for_update(reward_id)   # row lock
            if reward.stock <= 0:
                raise OutOfStock()
            balance = self._uow.ledger.balance(member_id, reward.campaign_id)
            if balance < reward.points_cost:
                raise InsufficientPoints()
            redemption = Redemption.create(member_id, reward, self._uow.clock.now())
            self._uow.redemptions.add(redemption)
            self._uow.ledger.add_entry(member_id, reward.campaign_id,
                                       delta=-reward.points_cost,
                                       reason="redeemed", ref_id=redemption.id)
            self._uow.rewards.decrement_stock(reward_id)
            self._uow.commit()
        return redemption
```

Rules: balance is always `SUM(delta)` from `points_ledger` (never a cached column);
lock the reward row (`SELECT ... FOR UPDATE`) so two redeems serialise; the balance
check and the negative ledger row live in the same transaction so they can't interleave.

## Health data writes go through a consent gate

Never write `health_record` without checking consent first — this is a PDPA obligation,
enforced in the use case:

```python
# application/use_cases/save_health_record.py
def execute(self, member_id, record) -> HealthRecord:
    if not self._consent.has_active(member_id, purpose="health_data"):
        raise ConsentRequired()
    return self._health.upsert(member_id, record)
```

See the security-pdpa skill for the admin-read + audit-log side.

## Testing

Fast, meaningful tests are the reason for the layering. Follow these patterns.

**Fake repositories** live in `tests/fakes/` — in-memory, no DB, no network:

```python
# tests/fakes/fake_run_repository.py
class FakeRunRepository:
    def __init__(self): self._items: list[RunEntry] = []
    def add(self, run): self._items.append(run)
    def list_by_member(self, member_id):
        return [r for r in self._items if r.member_id == member_id]
```

**A fixed clock** makes time deterministic:

```python
class FixedClock:
    def __init__(self, now): self._now = now
    def now(self): return self._now
```

**Unit-test the use case** with fakes — no framework in sight:

```python
def test_submit_run_persists():
    runs = FakeRunRepository()
    uc = SubmitRun(runs=runs, clock=FixedClock(datetime(2569 - 543, 6, 1)))
    uc.execute(SubmitRunCommand(member_id="u1", distance_km=5, duration_seconds=1800,
                                run_date=date(2026, 6, 1), evidence_key="k", source=...))
    assert len(runs.list_by_member("u1")) == 1
```

**Test each `CampaignPolicy` directly** — they're pure functions.

**Must-cover cases** (these protect money and the law):
- `redeem_reward`: rejects when balance < cost; two concurrent redeems don't drive the
  balance negative or oversell stock; a failed step rolls the whole transaction back.
- `save_health_record`: raises `ConsentRequired` when no active consent exists.

**Layer the tests**: `tests/domain/` (entities, policies), `tests/application/` (use
cases with fakes), `tests/api/` (a few endpoint smoke tests with the app wired to fakes).
Keep the DB out of unit tests; if you need a real-DB integration test, mark it and run
it separately, not in the fast gate.

## Anti-patterns — reject these in review

- `import fastapi` / `import sqlalchemy` inside `domain/` or `application/`.
- `member_id` read from the request body instead of the token.
- `if/elif` on `campaign.type` anywhere outside the policy registry.
- `float` for distance / points / cost (use `numeric` / `Decimal`).
- A cached points-balance column instead of summing the ledger.
- Business logic living in a router or in a Pydantic DTO.
- `datetime.now()` called inside a use case (inject the `Clock` port).
- Auto-running migrations on app startup.
