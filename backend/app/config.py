from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application config. Read from env / .env — never hardcode secrets."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    database_url: str

    # The only origin allowed to call this API. Never "*" — see security-pdpa #5.
    frontend_url: str = "http://localhost:3000"

    # Cloudflare sits in front of the API in production, and both of these describe that
    # arrangement. Off by default, because locally and in CI nothing is in front.
    #
    # cf_origin_secret: the shared value Cloudflare attaches to every request it
    #   forwards. Set it and the origin guard rejects anything arriving without it —
    #   which is how the service's public *.run.app URL stops being a way around the WAF.
    #   Empty disables the guard entirely.
    # trust_proxy: whether the CF-Connecting-IP header may be believed. Only ever true
    #   where the origin guard has already established Cloudflare is the sole way in;
    #   otherwise any caller could forge a new address per request and shed the limiter.
    cf_origin_secret: str = ""
    trust_proxy: bool = False

    # Clerk. The issuer and JWKS URL come from the Clerk instance; the webhook secret
    # signs the events we accept. All from env, never hardcoded.
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_webhook_secret: str = ""

    # Object storage: MinIO locally, Cloudflare R2 in production. Same code, different
    # endpoint. The bucket must be private in both.
    s3_bucket: str = "running-club-evidence"
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    evidence_url_ttl_seconds: int = 300

    # Gemini. Each extract call costs money, hence the tighter rate limit below.
    gemini_api_key: str = ""
    extract_rate_limit: str = "10/minute"

    # Requests per minute per member, applied to the whole API. Tighter per-route limits
    # go on the expensive endpoints (/runs/extract calls Gemini) when they exist.
    rate_limit: str = "120/minute"
    rate_limit_enabled: bool = True

    # Bootstrap only: when the Clerk webhook sees this clerk_user_id it promotes that
    # member to 'superuser'. Roles come from the verified webhook or this setting —
    # never from anything a client sends.
    superuser_clerk_user_id: str | None = None

    # The wording currently in force. Bump this ONLY when the consent text changes in
    # substance — every member who agreed to an older version is then treated as not
    # having consented, and must agree again before health data can be written.
    # That judgement is a human one; the code only compares the string.
    #
    # v2: the consent screen now tells members that their name and distance appear on
    # the club leaderboard. Anyone who agreed to v1 never saw that sentence, so counting
    # them as having agreed to it would be the one thing a consent record must never do.
    #
    # v2 is final. The hospital's DPO reviewed this wording and approved it unchanged, so
    # the v3 this comment used to expect never happened — the club launched on v2 and
    # members have consented under it. The next bump is whatever genuinely changes the
    # text next, not a review that is already done.
    consent_version: str = "v2"

    # Accountability logs outlive the data they describe: you must still be able to show
    # who accessed what, after that data has been purged. Purged by its own job, never
    # together with the member.
    # PLACEHOLDER: 5 years. Confirm against the club's actual PDPA retention policy.
    audit_retention_days: int = 1825

    # How long a health_record is kept after its campaign ends. Frozen onto each
    # record at write time (health_record.retention_until), so changing this only
    # affects records written afterwards — past promises stay as they were made.
    # PLACEHOLDER: 2 years. Confirm against the club's actual PDPA retention policy.
    health_retention_days: int = 730


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env


# Everything production cannot run correctly without. Most of these have a harmless
# default for local work (an empty Clerk issuer, no Gemini key), which is exactly why
# they need checking: a missing one does not announce itself at boot, it surfaces later
# as a 500 on every authenticated request, or a webhook that silently verifies nothing.
REQUIRED_IN_PRODUCTION = (
    "database_url",
    "clerk_issuer",
    "clerk_jwks_url",
    "clerk_webhook_secret",
    "superuser_clerk_user_id",
    "frontend_url",
    "s3_bucket",
    "s3_endpoint_url",
    "s3_access_key",
    "s3_secret_key",
    "gemini_api_key",
    "cf_origin_secret",
)


def missing_production_settings(settings: Settings) -> list[str]:
    """The env vars production needs and hasn't been given, by the name an operator sets.

    Only ever non-empty when APP_ENV=production: local and CI run with several of these
    blank on purpose.
    """
    if settings.app_env != "production":
        return []
    return [
        name.upper()
        for name in REQUIRED_IN_PRODUCTION
        if not str(getattr(settings, name) or "").strip()
    ]
