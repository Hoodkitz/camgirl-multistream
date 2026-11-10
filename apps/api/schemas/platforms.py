from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
from apps.core.models import Platform

class PlatformAccountCreate(BaseModel):
    tenant_id: UUID
    platform_name: Platform
    account_username: str
    stream_key: str

class PlatformAccountResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    platform_name: Platform
    account_username: str
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True
