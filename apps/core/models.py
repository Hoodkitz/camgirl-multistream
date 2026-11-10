"""Domain models."""
from enum import Enum
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Platform(str, Enum):
    CHATURBATE = "chaturbate"
    STRIPCHAT = "stripchat"
    MYFREECAMS = "myfreecams"
    BONGACAMS = "bongacams"
    CAMSODA = "camsoda"
    ORIENT = "orient"
    KINK = "kink"


class Tenant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    kms_kek_arn: str = "arn:aws:kms:us-east-1:123456789012:key/example"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class PlatformAccount(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    platform_name: Platform
    account_username: str
    encrypted_credentials: bytes
    wrapped_dek: bytes
    iv: bytes
    auth_tag: bytes
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True


class ChatMessage(BaseModel):
    event_id: str
    tenant_id: UUID
    stream_id: str
    platform: Platform
    event_type: str
    timestamp: datetime
    sender: dict
    payload: dict


class StreamSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    ingest_protocol: str = "rtmp"
    target_platforms: list[Platform] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None
    is_active: bool = True
    viewer_count: int = 0
    stats: dict = Field(default_factory=dict)
