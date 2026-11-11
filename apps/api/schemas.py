import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from apps.core.enums import EventType, Platform, Tier


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class TenantOut(ORM):
    id: uuid.UUID
    name: str
    tier: str
    created_at: datetime


class CredentialCreate(BaseModel):
    platform: Platform
    account_username: str = Field(min_length=1, max_length=255)
    stream_key: str = Field(min_length=4, max_length=512, description="Portal-Stream-Key (wird verschluesselt)")
    api_token: str | None = Field(default=None, max_length=4096, description="optional: Chat-API-Token/Passwort")
    ingest_url: str | None = Field(default=None, pattern=r"^rtmps?://[^\s]+$", max_length=500)


class CredentialOut(ORM):
    id: uuid.UUID
    platform: str
    account_username: str
    ingest_url: str | None
    enabled: bool
    created_at: datetime


class StreamKeyCreate(BaseModel):
    label: str = Field(default="Standard", max_length=100)


class StreamKeyOut(ORM):
    id: uuid.UUID
    label: str
    revoked: bool
    created_at: datetime


class StreamKeyCreated(StreamKeyOut):
    stream_key: str
    rtmp_url: str
    srt_url: str


class SrsHook(BaseModel):
    """SRS HTTP-Callback (on_publish / on_unpublish)."""
    action: str
    client_id: str
    ip: str | None = None
    app: str = "live"
    stream: str
    param: str | None = None


class TargetOut(BaseModel):
    platform: str
    account_username: str
    url: str  # enthaelt den Portal-Stream-Key -> nur an SRS bzw. den Owner


class SessionOut(ORM):
    id: uuid.UUID
    protocol: str
    targets: list[str]
    tip_total: int
    goal_reached: bool
    started_at: datetime
    ended_at: datetime | None
    end_reason: str | None


class Sender(BaseModel):
    platform_user_id: str | None = Field(default=None, max_length=128)
    username: str | None = Field(default=None, max_length=255)
    badge_level: str | None = Field(default=None, max_length=50)


class EventPayload(BaseModel):
    message: str | None = Field(default=None, max_length=4000)
    tokens_spent: int = Field(default=0, ge=0, le=10_000_000)
    fiat_equivalent_usd: float = Field(default=0.0, ge=0)
    is_private_request: bool = False


class PortalEvent(BaseModel):
    """Normalisiertes Event-Schema (Spec Kap. 5.1)."""
    event_id: str = Field(min_length=1, max_length=128)
    tenant_id: uuid.UUID
    stream_id: str | None = Field(default=None, max_length=128)
    platform: Platform
    event_type: EventType
    timestamp: datetime
    sender: Sender = Sender()
    payload: EventPayload = EventPayload()


class ReplyIn(BaseModel):
    platform: Platform
    text: str = Field(min_length=1, max_length=1000)
    recipient: str | None = Field(default=None, max_length=255, description="None = oeffentlicher Chat")


class AutomationIn(BaseModel):
    greet_enabled: bool = False
    greet_template: str = Field(default="Hey {username}, willkommen! 💕", min_length=1, max_length=500)
    greet_cooldown_hours: int = Field(default=24, ge=1, le=24 * 30)
    greet_platforms: list[Platform] = []
    tip_goal_tokens: int | None = Field(default=None, ge=1)
    tip_goal_label: str | None = Field(default=None, max_length=200)
    obs_webhook_url: HttpUrl | None = None

    @field_validator("obs_webhook_url")
    @classmethod
    def _https_or_local(cls, v):
        if v and v.scheme != "https" and v.host not in ("localhost", "127.0.0.1"):
            raise ValueError("OBS-Webhook muss https sein")
        return v


class AutomationOut(ORM):
    greet_enabled: bool
    greet_template: str
    greet_cooldown_hours: int
    greet_platforms: list[str]
    tip_goal_tokens: int | None
    tip_goal_label: str | None
    obs_webhook_url: str | None


class DevTokenRequest(BaseModel):
    sub: str
    tenant_id: uuid.UUID
    roles: list[str]
    tier: Tier | None = None
