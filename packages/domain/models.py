"""Domain models for CamGirl Multi-Stream SaaS."""
from enum import Enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Platform(str, Enum):
    CHATURBATE = "chaturbate"
    STRIPCHAT = "stripchat"
    MYFREECAMS = "myfreecams"
    BONGACAMS = "bongacams"
    CAMSODA = "camsoda"


class Tenant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    kms_kek_arn: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


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


class ChatEvent(BaseModel):
    event_id: str
    tenant_id: UUID
    stream_id: str
    platform: Platform
    event_type: str  # "message", "tip", "follow", "subscribe"
    timestamp: datetime
    sender: dict
    payload: dict


class StreamSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    ingest_protocol: str  # "rtmp" or "srt"
    target_platforms: List[Platform] = []
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    is_active: bool = True
