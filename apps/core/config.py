"""Konfiguration (Umgebungsvariablen / .env). Default ENV=prod -> fail closed."""
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-secret-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "prod"
    DATABASE_URL: str = "sqlite+aiosqlite:///./camgirl-dev.db"
    # Systemrolle (BYPASSRLS) fuer mandantenuebergreifende Callbacks: SRS-Key-Lookup, Outbox-Worker, Webhooks
    SYSTEM_DATABASE_URL: str | None = None
    AUTO_CREATE_TABLES: bool = True

    JWT_SECRET: str = _DEV_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_AUDIENCE: str = "multistream-api"
    OIDC_ISSUER: str = "https://auth.example.invalid"
    ACCESS_TOKEN_MINUTES: int = 15

    # Maschinen-zu-Maschinen-Secrets (SRS-Callback, Platform Connectors, Stripe)
    SRS_CALLBACK_SECRET: str = "dev-srs-secret"
    SRS_ALLOWED_IPS: str = "127.0.0.1,testclient"
    CONNECTOR_SECRET: str = "dev-connector-secret"
    STRIPE_WEBHOOK_SECRET: str = "whsec_dev"
    OBS_WEBHOOK_SECRET: str = "dev-obs-secret"

    # Lokaler KMS-Ersatz: Master-Key (base64, 32 Byte). In Produktion: Cloud-KMS/HSM.
    LOCAL_KMS_MASTER_KEY: str = "ZGV2LW1hc3Rlci1rZXktZG8tbm90LXVzZS1pbi1wciE="

    CORS_ORIGINS: str = "http://localhost:3000"
    RATE_LIMIT_PER_MINUTE: int = 60
    CHAT_RETENTION_DAYS: int = 30
    STREAM_WALL_TIME_HOURS: int = 24

    @property
    def dev_endpoints_enabled(self) -> bool:
        return self.ENV in ("dev", "test")


settings = Settings()

if not settings.dev_endpoints_enabled:
    weak = [k for k in ("JWT_SECRET", "SRS_CALLBACK_SECRET", "CONNECTOR_SECRET", "STRIPE_WEBHOOK_SECRET",
                        "OBS_WEBHOOK_SECRET") if getattr(settings, k).startswith(("dev", "whsec_dev"))]
    if weak or settings.LOCAL_KMS_MASTER_KEY.startswith("ZGV2"):
        raise RuntimeError(f"Produktions-Secrets fehlen: {weak or ['LOCAL_KMS_MASTER_KEY']}")
