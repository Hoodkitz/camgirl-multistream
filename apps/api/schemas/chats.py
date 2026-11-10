"""Pydantic schemas for Chats."""
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class ChatIngest(BaseModel):
    event_id: str
    tenant_id: UUID
    stream_id: str
    platform: str
    event_type: str
    timestamp: datetime
    sender: dict
    payload: dict


class ChatResponse(BaseModel):
    tenant_id: UUID
    platform: str
    recipient: str
    content: str
    is_automated: bool = False


class ChatMessageCreate(BaseModel):
    tenant_id: UUID
    platform: str
    sender: dict
    content: str
    msg_type: str = "message"


class ChatMessageResponse(BaseModel):
    message_id: str
    sender: str
    content: str
    timestamp: datetime
    is_automated: bool = False
