"""Pydantic schemas for Stats."""
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from enum import Enum


class StreamStatus(str, Enum):
    ACTIVE = "active"
    STOPPED = "stopped"


class StreamStatsResponse(BaseModel):
    stream_id: UUID
    viewer_count: int
    duration_seconds: int
    target_platforms: list[str]
    started_at: datetime
    ended_at: datetime | None


class TenantStatsResponse(BaseModel):
    tenant_id: UUID
    active_streams: int
    total_viewers: int
    total_streams: int
    sessions: list[dict]
