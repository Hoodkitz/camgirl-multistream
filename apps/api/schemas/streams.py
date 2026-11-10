"""Pydantic schemas for CamGirl Multi-Stream."""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from enum import Enum
from ..core.models import Platform


class StreamCreate(BaseModel):
    tenant_id: UUID
    ingest_protocol: str = "rtmp"
    target_platforms: list[Platform] = Field(min_length=1)


class StreamResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    ingest_protocol: str
    target_platforms: list[Platform]
    started_at: datetime
    ended_at: datetime | None
    is_active: bool
    viewer_count: int
    stats: dict

    class Config:
        from_attributes = True


class StreamSessionCreate(BaseModel):
    tenant_id: UUID
    ingest_protocol: str = "rtmp"
    target_platforms: list[str]


class StreamSessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    ingest_protocol: str
    target_platforms: list[str]
    started_at: datetime
    ended_at: datetime | None
    is_active: bool
    viewer_count: int

    class Config:
        from_attributes = True
