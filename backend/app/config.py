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
    consent_version: str = "v1"

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
