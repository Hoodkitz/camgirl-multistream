"""SQLAlchemy-Modelle; alle Mandantentabellen tragen tenant_id (RLS, Spec Kap. 7)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def _tenant_fk():
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    tier: Mapped[str] = mapped_column(String(20), default="standard")
    kek_ref: Mapped[str] = mapped_column(String(255))
    kek_blob: Mapped[bytes | None] = mapped_column(LargeBinary)  # nur LocalKMS; Cloud-KMS haelt den KEK selbst
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "platform", "account_username"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    platform: Mapped[str] = mapped_column(String(32))
    account_username: Mapped[str] = mapped_column(String(255))
    ingest_url: Mapped[str | None] = mapped_column(String(500))
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    iv: Mapped[bytes] = mapped_column(LargeBinary)
    auth_tag: Mapped[bytes] = mapped_column(LargeBinary)
    kek_ref: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StreamKey(Base):
    __tablename__ = "stream_keys"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    label: Mapped[str] = mapped_column(String(100), default="Standard")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StreamSession(Base):
    __tablename__ = "stream_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    stream_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stream_keys.id", ondelete="CASCADE"))
    srs_client_id: Mapped[str] = mapped_column(String(100))
    protocol: Mapped[str] = mapped_column(String(10), default="rtmp")
    targets: Mapped[list] = mapped_column(JSON, default=list)  # nur Plattformnamen, nie Keys
    tip_total: Mapped[int] = mapped_column(Integer, default=0)
    goal_reached: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    end_reason: Mapped[str | None] = mapped_column(String(50))


class ChatEvent(Base):
    __tablename__ = "chat_events"
    __table_args__ = (UniqueConstraint("tenant_id", "event_id"),)  # Idempotenz (ADR-07)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    event_id: Mapped[str] = mapped_column(String(128))
    stream_id: Mapped[str | None] = mapped_column(String(128))
    platform: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    sender_id: Mapped[str | None] = mapped_column(String(128))
    sender_name: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    fiat_usd: Mapped[float] = mapped_column(Float, default=0.0)
    is_outgoing: Mapped[bool] = mapped_column(Boolean, default=False)
    is_automated: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AutomationSettings(Base):
    __tablename__ = "automation_settings"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    greet_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    greet_template: Mapped[str] = mapped_column(Text, default="Hey {username}, willkommen! 💕")
    greet_cooldown_hours: Mapped[int] = mapped_column(Integer, default=24)
    greet_platforms: Mapped[list] = mapped_column(JSON, default=list)  # leer = alle
    tip_goal_tokens: Mapped[int | None] = mapped_column(Integer)
    tip_goal_label: Mapped[str | None] = mapped_column(String(200))
    obs_webhook_url: Mapped[str | None] = mapped_column(String(500))


class GreetLog(Base):
    __tablename__ = "greet_log"
    __table_args__ = (UniqueConstraint("tenant_id", "platform", "sender_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    platform: Mapped[str] = mapped_column(String(32))
    sender_id: Mapped[str] = mapped_column(String(128))
    last_greeted: Mapped[datetime] = mapped_column(DateTime)


class Outbox(Base):
    """Transactional Outbox (ADR-06): Chat-Antworten an Portale, OBS-Webhooks."""
    __tablename__ = "transactional_outbox"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING | DONE | DEAD
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WebhookInbox(Base):
    __tablename__ = "webhook_inbox"
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
