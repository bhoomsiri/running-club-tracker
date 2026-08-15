"""Wiring: the single place where abstractions meet implementations.

Also the single place `member_id` enters the application. Every endpoint takes it from
`get_current_member_id`, which derives it from a verified token — never from a path, a
query string, or a body (golden rule #2).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.auth.clerk_authenticator import ClerkAuthenticator
from app.adapters.auth.clerk_webhook import ClerkWebhookVerifier
from app.adapters.extraction.gemini_extractor import GeminiExtractor
from app.adapters.persistence.admin_unit_of_work import SqlAlchemyAdminUnitOfWork
from app.adapters.persistence.health_unit_of_work import SqlAlchemyHealthUnitOfWork
from app.adapters.persistence.run_review_unit_of_work import SqlAlchemyRunReviewUnitOfWork
from app.adapters.persistence.run_submission_unit_of_work import (
    SqlAlchemyRunSubmissionUnitOfWork,
)
from app.adapters.persistence.sensitive_view_unit_of_work import (
    SqlAlchemySensitiveViewUnitOfWork,
)
from app.adapters.persistence.sqlalchemy_campaign_repository import (
    SqlAlchemyCampaignRepository,
)
from app.adapters.persistence.sqlalchemy_consent_repository import SqlAlchemyConsentRepository
from app.adapters.persistence.sqlalchemy_health_repository import SqlAlchemyHealthRepository
from app.adapters.persistence.sqlalchemy_member_repository import SqlAlchemyMemberRepository
from app.adapters.persistence.sqlalchemy_points_ledger_repository import (
    SqlAlchemyPointsLedgerRepository,
)
from app.adapters.persistence.sqlalchemy_redemption_repository import (
    SqlAlchemyRedemptionRepository,
)
from app.adapters.persistence.sqlalchemy_reward_repository import SqlAlchemyRewardRepository
from app.adapters.persistence.sqlalchemy_run_repository import SqlAlchemyRunRepository
from app.adapters.persistence.sqlalchemy_screening_repository import (
    SqlAlchemyScreeningRepository,
)
from app.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.adapters.storage.pillow_image_sanitizer import PillowImageSanitizer
from app.adapters.storage.s3_image_storage import S3ImageStorage
from app.application.ports.image_storage import ImageStorage
from app.application.ports.run_extractor import RunExtractor
from app.application.ports.token_verifier import TokenVerifier
from app.application.use_cases.ensure_member import EnsureMember
from app.application.use_cases.extract_run_draft import ExtractRunDraft
from app.application.use_cases.get_club_overview import GetClubOverview
from app.application.use_cases.get_my_consent import GetMyConsent
from app.application.use_cases.get_my_screening import GetMyScreening
from app.application.use_cases.get_my_summary import GetMySummary
from app.application.use_cases.get_onboarding_status import GetOnboardingStatus
from app.application.use_cases.grant_consent import GrantConsent
from app.application.use_cases.list_members import ListMembers
from app.application.use_cases.list_rewards import ListRewards
from app.application.use_cases.list_runs import ListMemberRuns, ListMyRuns
from app.application.use_cases.manage_campaigns import CreateCampaign, UpdateCampaign
from app.application.use_cases.manage_redemptions import CancelRedemption, FulfillRedemption
from app.application.use_cases.manage_rewards import CreateReward, UpdateReward
from app.application.use_cases.redeem_reward import RedeemReward
from app.application.use_cases.review_run import ReviewRun
from app.application.use_cases.save_health_record import SaveHealthRecord
from app.application.use_cases.save_my_screening import SaveMyScreening
from app.application.use_cases.submit_run import SubmitRun
from app.application.use_cases.sync_member_from_clerk import SyncMemberFromClerk
from app.application.use_cases.update_my_profile import UpdateMyProfile
from app.application.use_cases.upload_evidence import UploadEvidence
from app.application.use_cases.view_member_contact import ViewMemberContact
from app.application.use_cases.view_member_health import ViewMemberHealth
from app.application.use_cases.view_member_progress import ViewMemberProgress
from app.application.use_cases.view_member_screening import ViewMemberScreening
from app.application.use_cases.withdraw_consent import WithdrawConsent
from app.config import Settings, get_settings
from app.db import get_session_factory
from app.domain.entities import Member
from app.domain.errors import InvalidToken, MemberNotFound, NotAuthorized

# auto_error=False so a missing header reaches our own handler and returns a consistent
# 401 body instead of FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False)


class SystemClock:
    """The one place `datetime.now()` is allowed to be called."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def get_clock() -> SystemClock:
    return SystemClock()


def get_settings_dep() -> Settings:
    return get_settings()


def get_session_factory_dep() -> sessionmaker[Session]:
    return get_session_factory()


def get_session(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@lru_cache(maxsize=4)
def _authenticator(
    jwks_url: str, issuer: str, authorized_party: str
) -> ClerkAuthenticator:
    """Cached on plain strings, NOT on the Settings object.

    `Settings` is a pydantic model and therefore unhashable, so caching on it raised
    TypeError on every authenticated request. The cache matters: it keeps PyJWKClient's
    fetched signing keys alive between requests instead of hitting Clerk's JWKS endpoint
    each time.
    """
    return ClerkAuthenticator(
        jwks_url=jwks_url, issuer=issuer, authorized_parties=[authorized_party]
    )


def get_token_verifier(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> TokenVerifier:
    return _authenticator(
        settings.clerk_jwks_url, settings.clerk_issuer, settings.frontend_url
    )


def get_webhook_verifier(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ClerkWebhookVerifier:
    return ClerkWebhookVerifier(settings.clerk_webhook_secret)


# ------------------------------------------------------------------ identity & roles


def get_current_member(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> Member:
    if credentials is None or not credentials.credentials:
        raise InvalidToken("authorization header is missing")

    identity = verifier.verify(credentials.credentials)
    # Just-in-time provisioning: a verified member whose webhook hasn't landed yet still
    # gets in, as an ordinary member. Roles are never taken from the token.
    member = EnsureMember(SqlAlchemyMemberRepository(session), clock).execute(identity)
    request.state.member_id = member.id
    return member


def get_current_member_id(
    member: Annotated[Member, Depends(get_current_member)],
) -> UUID:
    return member.id


def get_current_admin(
    member: Annotated[Member, Depends(get_current_member)],
) -> Member:
    """Admin or superuser. The role is read from the member row loaded above — a role
    claim inside a token is never consulted."""
    if not member.role.may_view_others_health:
        raise NotAuthorized("admin only")
    return member


def get_current_superuser(
    member: Annotated[Member, Depends(get_current_member)],
) -> Member:
    if not member.role.may_edit_records:
        raise NotAuthorized("superuser only")
    return member


def require_member(session: Session, member_id: UUID) -> Member:
    member = SqlAlchemyMemberRepository(session).get(member_id)
    if member is None:
        raise MemberNotFound(str(member_id))
    return member


# ----------------------------------------------------------------------- use cases


def get_my_summary_uc(
    session: Annotated[Session, Depends(get_session)],
) -> GetMySummary:
    return GetMySummary(
        members=SqlAlchemyMemberRepository(session),
        runs=SqlAlchemyRunRepository(session),
        campaigns=SqlAlchemyCampaignRepository(session),
        ledger=SqlAlchemyPointsLedgerRepository(session),
        redemptions=SqlAlchemyRedemptionRepository(session),
        health=SqlAlchemyHealthRepository(session),
    )


def get_grant_consent_uc(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> GrantConsent:
    return GrantConsent(SqlAlchemyConsentRepository(session), clock, settings.consent_version)


def get_my_consent_uc(
    session: Annotated[Session, Depends(get_session)],
) -> GetMyConsent:
    return GetMyConsent(SqlAlchemyConsentRepository(session))


def get_withdraw_consent_uc(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> WithdrawConsent:
    return WithdrawConsent(SqlAlchemyConsentRepository(session), clock)


def get_save_health_uc(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> SaveHealthRecord:
    return SaveHealthRecord(
        consents=SqlAlchemyConsentRepository(session),
        campaigns=SqlAlchemyCampaignRepository(session),
        health=SqlAlchemyHealthRepository(session),
        clock=clock,
        consent_version=settings.consent_version,
        retention_days=settings.health_retention_days,
    )


def get_update_profile_uc(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> UpdateMyProfile:
    return UpdateMyProfile(SqlAlchemyMemberRepository(session), clock)


def get_my_screening_uc(
    session: Annotated[Session, Depends(get_session)],
) -> GetMyScreening:
    return GetMyScreening(SqlAlchemyScreeningRepository(session))


def get_save_screening_uc(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> SaveMyScreening:
    return SaveMyScreening(
        consents=SqlAlchemyConsentRepository(session),
        screenings=SqlAlchemyScreeningRepository(session),
        clock=clock,
        consent_version=settings.consent_version,
    )


def get_onboarding_status_uc(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> GetOnboardingStatus:
    return GetOnboardingStatus(
        members=SqlAlchemyMemberRepository(session),
        consents=SqlAlchemyConsentRepository(session),
        screenings=SqlAlchemyScreeningRepository(session),
        health=SqlAlchemyHealthRepository(session),
        consent_version=settings.consent_version,
    )


def get_club_overview_uc(
    session: Annotated[Session, Depends(get_session)],
) -> GetClubOverview:
    return GetClubOverview(
        members=SqlAlchemyMemberRepository(session),
        runs=SqlAlchemyRunRepository(session),
        campaigns=SqlAlchemyCampaignRepository(session),
        ledger=SqlAlchemyPointsLedgerRepository(session),
    )


def get_list_members_uc(
    session: Annotated[Session, Depends(get_session)],
) -> ListMembers:
    return ListMembers(SqlAlchemyMemberRepository(session))


def get_view_member_health_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ViewMemberHealth:
    # Its own UnitOfWork, not the request session: the audit row and the read must
    # commit together, before the data is returned.
    return ViewMemberHealth(
        SqlAlchemyHealthUnitOfWork(factory, clock), settings.consent_version
    )


def get_view_member_progress_uc(
    session: Annotated[Session, Depends(get_session)],
) -> ViewMemberProgress:
    # Not audited: distance and points are activity records, not sensitive data.
    return ViewMemberProgress(
        members=SqlAlchemyMemberRepository(session),
        runs=SqlAlchemyRunRepository(session),
        campaigns=SqlAlchemyCampaignRepository(session),
        ledger=SqlAlchemyPointsLedgerRepository(session),
        redemptions=SqlAlchemyRedemptionRepository(session),
    )


def get_view_member_screening_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> ViewMemberScreening:
    # Its own UnitOfWork: the audit row and the read commit together, audit first.
    return ViewMemberScreening(SqlAlchemySensitiveViewUnitOfWork(factory, clock))


def get_view_member_contact_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> ViewMemberContact:
    return ViewMemberContact(SqlAlchemySensitiveViewUnitOfWork(factory, clock))


def get_redeem_reward_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> RedeemReward:
    # Its own UnitOfWork: the reward row lock, the account lock, the balance check and
    # both writes have to be one transaction, not the request-scoped session.
    return RedeemReward(SqlAlchemyUnitOfWork(factory, clock))


def get_sync_member_uc(
    session: Annotated[Session, Depends(get_session)],
    clock: Annotated[SystemClock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> SyncMemberFromClerk:
    return SyncMemberFromClerk(
        SqlAlchemyMemberRepository(session), clock, settings.superuser_clerk_user_id
    )


# ------------------------------------------------------------------ storage & runs


def get_image_storage(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ImageStorage:
    # MinIO locally, R2 in production: same class, different endpoint from env.
    return S3ImageStorage(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )


def get_run_extractor(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> RunExtractor:
    return GeminiExtractor(api_key=settings.gemini_api_key)


def get_upload_evidence_uc(
    storage: Annotated[ImageStorage, Depends(get_image_storage)],
) -> UploadEvidence:
    return UploadEvidence(storage, PillowImageSanitizer())


def get_extract_run_uc(
    storage: Annotated[ImageStorage, Depends(get_image_storage)],
    extractor: Annotated[RunExtractor, Depends(get_run_extractor)],
) -> ExtractRunDraft:
    return ExtractRunDraft(storage, extractor)


def get_submit_run_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> SubmitRun:
    # Its own UnitOfWork: the run and the points it earns commit together.
    return SubmitRun(SqlAlchemyRunSubmissionUnitOfWork(factory, clock))


def get_review_run_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> ReviewRun:
    # Decision + points + audit commit together.
    return ReviewRun(SqlAlchemyRunReviewUnitOfWork(factory, clock))


def get_list_rewards_uc(
    session: Annotated[Session, Depends(get_session)],
) -> ListRewards:
    return ListRewards(
        SqlAlchemyCampaignRepository(session),
        SqlAlchemyRewardRepository(session),
        SqlAlchemyPointsLedgerRepository(session),
    )


def get_list_my_runs_uc(
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ImageStorage, Depends(get_image_storage)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ListMyRuns:
    return ListMyRuns(
        SqlAlchemyRunRepository(session),
        storage,
        timedelta(seconds=settings.evidence_url_ttl_seconds),
    )


def get_list_member_runs_uc(
    session: Annotated[Session, Depends(get_session)],
    storage: Annotated[ImageStorage, Depends(get_image_storage)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ListMemberRuns:
    return ListMemberRuns(
        SqlAlchemyMemberRepository(session),
        SqlAlchemyRunRepository(session),
        storage,
        timedelta(seconds=settings.evidence_url_ttl_seconds),
    )


# ------------------------------------------------------------- superuser mutations
# All of these share one AdminUnitOfWork factory: the change and its audit row commit
# together, always.


def _admin_uow(
    factory: sessionmaker[Session], clock: SystemClock
) -> SqlAlchemyAdminUnitOfWork:
    return SqlAlchemyAdminUnitOfWork(factory, clock)


def get_create_campaign_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> CreateCampaign:
    return CreateCampaign(_admin_uow(factory, clock))


def get_update_campaign_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> UpdateCampaign:
    return UpdateCampaign(_admin_uow(factory, clock))


def get_create_reward_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> CreateReward:
    return CreateReward(_admin_uow(factory, clock))


def get_update_reward_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> UpdateReward:
    return UpdateReward(_admin_uow(factory, clock))


def get_fulfill_redemption_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> FulfillRedemption:
    return FulfillRedemption(_admin_uow(factory, clock))


def get_cancel_redemption_uc(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory_dep)],
    clock: Annotated[SystemClock, Depends(get_clock)],
) -> CancelRedemption:
    return CancelRedemption(_admin_uow(factory, clock))
