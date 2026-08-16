"""Catalogue photos: who may upload one, where it lands, and what a reward may point at.

The security question here is not the upload — it is the pointer. A reward's `image_key`
arrives from a client and the rewards page mints a presigned URL for whatever it names,
handing that link to every member who opens the page. A key pointing into `runs/` would
therefore publish another member's evidence photo to the whole club. Most of this file is
about that one line.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.use_cases.list_rewards import ListRewards
from app.application.use_cases.manage_rewards import (
    CreateReward,
    CreateRewardCommand,
    UpdateReward,
    UpdateRewardCommand,
)
from app.application.use_cases.upload_reward_image import (
    UploadRewardImage,
    UploadRewardImageCommand,
)
from app.domain.campaign import Campaign, CampaignType
from app.domain.entities import Member, MemberRole
from app.domain.errors import InvalidImage, InvalidRewardError, NotAuthorized
from app.domain.evidence import ImageKind
from app.domain.redemption import Reward
from tests.fakes.fake_storage import FakeImageStorage, PassthroughSanitizer
from tests.fakes.fake_uow import (
    FakeAdminUnitOfWork,
    FakeAuditRepository,
    FakePointsLedgerRepository,
    FakeRedemptionRepository,
    FakeRewardRepository,
    FixedClock,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeMemberRepository,
    FakeRunRepository,
)

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200

CAMPAIGN = Campaign(
    id=uuid4(),
    code="run-to-earn-2026",
    name="วิ่งสะสมแต้มแลกของรางวัล",
    type=CampaignType.REDEEM_REWARD,
    starts_on=date(2026, 1, 1),
    ends_on=date(2026, 12, 31),
    config={"km_per_point": "1"},
    is_active=True,
)


def a_member(role: MemberRole) -> Member:
    return Member.create(
        clerk_user_id=f"user_{role.value}", display_name=role.value, now=NOW, role=role
    )


BOSS = a_member(MemberRole.SUPERUSER)
ADMIN = a_member(MemberRole.ADMIN)
RUNNER = a_member(MemberRole.MEMBER)


def a_reward(**overrides: object) -> Reward:
    fields: dict[str, object] = {
        "id": uuid4(),
        "campaign_id": CAMPAIGN.id,
        "name": "เสื้อวิ่ง",
        "points_cost": Decimal("5"),
        "stock": 3,
        "is_active": True,
    }
    fields.update(overrides)
    return Reward(**fields)  # type: ignore[arg-type]


class Harness:
    """The same wiring the admin management tests use, plus storage."""

    def __init__(self, rewards: list[Reward] | None = None) -> None:
        self.members = FakeMemberRepository([BOSS, ADMIN, RUNNER])
        self.campaigns = FakeCampaignRepository([CAMPAIGN])
        self.rewards = FakeRewardRepository(rewards or [])
        self.ledger = FakePointsLedgerRepository()
        self.audit = FakeAuditRepository()
        self.storage = FakeImageStorage()

    def uow(self) -> FakeAdminUnitOfWork:
        return FakeAdminUnitOfWork(
            members=self.members,
            campaigns=self.campaigns,
            rewards=self.rewards,
            redemptions=FakeRedemptionRepository(),
            runs=FakeRunRepository(),
            ledger=self.ledger,
            audit=self.audit,
            clock=FixedClock(NOW),
        )

    def upload(self) -> UploadRewardImage:
        return UploadRewardImage(self.members, self.storage, PassthroughSanitizer())


class TestUpload:
    def test_the_superuser_can_upload_a_photo(self) -> None:
        harness = Harness()

        stored = harness.upload().execute(
            UploadRewardImageCommand(actor_id=BOSS.id, data=JPEG)
        )

        assert stored.image_key in harness.storage.objects
        assert harness.storage.objects[stored.image_key][1] == "image/jpeg"

    def test_it_lands_outside_every_member_folder(self) -> None:
        """`is_owned_by` reads ownership out of the key, so a catalogue photo filed under
        runs/<member> would look like that member's evidence."""
        harness = Harness()

        stored = harness.upload().execute(
            UploadRewardImageCommand(actor_id=BOSS.id, data=JPEG)
        )

        assert stored.image_key.startswith("rewards/")
        assert not stored.image_key.startswith("runs/")

    def test_the_key_is_the_content_hash(self) -> None:
        """So the same photo uploaded twice is one object, not two."""
        harness = Harness()

        first = harness.upload().execute(UploadRewardImageCommand(actor_id=BOSS.id, data=JPEG))
        second = harness.upload().execute(UploadRewardImageCommand(actor_id=BOSS.id, data=JPEG))

        assert first.image_key == second.image_key
        # Hashed AFTER scrubbing, like evidence: two copies of one photo whose metadata
        # differed are still one object.
        assert hashlib.sha256(b"scrubbed:" + JPEG).hexdigest() in first.image_key

    def test_the_sanitizer_runs_before_anything_is_stored(self) -> None:
        """A product photo carries EXIF as readily as a member's — including where it
        was taken."""
        harness = Harness()
        sanitizer = PassthroughSanitizer()

        UploadRewardImage(harness.members, harness.storage, sanitizer).execute(
            UploadRewardImageCommand(actor_id=BOSS.id, data=JPEG)
        )

        assert sanitizer.calls == [ImageKind.JPEG.value]

    @pytest.mark.parametrize("actor", [ADMIN, RUNNER])
    def test_nobody_else_can_upload(self, actor: Member) -> None:
        """Not even an admin: this writes to storage the club pays for and the result is
        shown to every member."""
        harness = Harness()

        with pytest.raises(NotAuthorized):
            harness.upload().execute(
                UploadRewardImageCommand(actor_id=actor.id, data=JPEG)
            )

        assert harness.storage.objects == {}

    def test_a_file_that_is_not_an_image_is_refused(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidImage):
            harness.upload().execute(
                UploadRewardImageCommand(
                    actor_id=BOSS.id, data=b"<?php system($_GET['c']); ?>" + b" " * 200
                )
            )


class TestTheKeyARewardMayPointAt:
    """The IDOR: `image_key` is client-supplied, and every member is handed a URL for
    whatever it names."""

    def test_creating_with_a_run_evidence_key_is_refused(self) -> None:
        harness = Harness()
        someone_elses_photo = f"runs/{RUNNER.id}/{'a' * 64}.jpeg"

        with pytest.raises(InvalidRewardError, match="image_key"):
            CreateReward(harness.uow()).execute(
                CreateRewardCommand(
                    actor_id=BOSS.id,
                    campaign_id=CAMPAIGN.id,
                    name="เสื้อวิ่ง",
                    points_cost=Decimal("5"),
                    stock=1,
                    image_key=someone_elses_photo,
                )
            )

    def test_updating_to_a_run_evidence_key_is_refused(self) -> None:
        reward = a_reward()
        harness = Harness(rewards=[reward])

        with pytest.raises(InvalidRewardError, match="image_key"):
            UpdateReward(harness.uow()).execute(
                UpdateRewardCommand(
                    actor_id=BOSS.id,
                    reward_id=reward.id,
                    image_key=f"runs/{RUNNER.id}/{'b' * 64}.jpeg",
                )
            )

        assert harness.rewards.get(reward.id) == reward

    def test_a_photo_can_be_attached_and_replaced(self) -> None:
        first = f"rewards/{'c' * 64}.jpeg"
        second = f"rewards/{'d' * 64}.png"
        reward = a_reward(image_key=first)
        harness = Harness(rewards=[reward])

        updated = UpdateReward(harness.uow()).execute(
            UpdateRewardCommand(actor_id=BOSS.id, reward_id=reward.id, image_key=second)
        )

        assert updated.image_key == second

    def test_omitting_it_leaves_the_photo_alone(self) -> None:
        """Every field on this command means 'unchanged' when omitted, and the photo is
        no exception — restocking must not silently drop the picture."""
        key = f"rewards/{'e' * 64}.jpeg"
        reward = a_reward(image_key=key)
        harness = Harness(rewards=[reward])

        updated = UpdateReward(harness.uow()).execute(
            UpdateRewardCommand(actor_id=BOSS.id, reward_id=reward.id, stock=9)
        )

        assert updated.image_key == key


class TestTheMemberCatalogue:
    def build(self, harness: Harness) -> ListRewards:
        return ListRewards(
            harness.campaigns, harness.rewards, harness.ledger, harness.storage
        )

    def test_a_reward_with_a_photo_arrives_with_a_link(self) -> None:
        key = f"rewards/{'f' * 64}.jpeg"
        harness = Harness(rewards=[a_reward(image_key=key)])

        catalogue = self.build(harness).execute(RUNNER.id)

        offer = catalogue[0].rewards[0]
        assert offer.image_url is not None
        assert key in offer.image_url

    def test_a_reward_without_one_arrives_with_none(self) -> None:
        """Rather than a broken link: a reward is perfectly usable without a picture."""
        harness = Harness(rewards=[a_reward()])

        catalogue = self.build(harness).execute(RUNNER.id)

        assert catalogue[0].rewards[0].image_url is None
        assert harness.storage.signed == []

    def test_only_catalogue_keys_are_ever_signed(self) -> None:
        """The other half of the IDOR check, from the reading end."""
        harness = Harness(
            rewards=[a_reward(image_key=f"rewards/{'0' * 64}.jpeg"), a_reward()]
        )

        self.build(harness).execute(RUNNER.id)

        assert all(key.startswith("rewards/") for key, _ in harness.storage.signed)

    def test_the_link_expires(self) -> None:
        harness = Harness(rewards=[a_reward(image_key=f"rewards/{'1' * 64}.jpeg")])

        self.build(harness).execute(RUNNER.id)

        _, ttl = harness.storage.signed[0]
        assert 0 < ttl.total_seconds() <= 600
