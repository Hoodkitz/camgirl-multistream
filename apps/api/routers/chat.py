"""Chat API endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["chat"])
_aggregator = None


def get_aggregator():
    global _aggregator
    if _aggregator is None:
        from packages.storage.chat_aggregator import ChatAggregator
        _aggregator = ChatAggregator()
    return _aggregator


class ChatIngest(BaseModel):
    tenant_id: UUID
    platform: str
    sender: str
    content: str
    msg_type: str = "message"


class ChatReply(BaseModel):
    tenant_id: UUID
    platform: str
    recipient: str
    content: str


@router.post("/chat/ingest")
async def ingest_chat(req: ChatIngest):
    agg = get_aggregator()
    msg = agg.ingest_message(str(req.tenant_id), req.platform, req.sender, req.content, req.msg_type)
    return msg


@router.get("/chat/inbox/{tenant_id}")
async def unified_inbox(tenant_id: UUID, limit: int = 50):
    agg = get_aggregator()
    return {"messages": agg.get_unified_inbox(str(tenant_id), limit)}


@router.get("/chat/platform/{tenant_id}/{platform}")
async def platform_messages(tenant_id: UUID, platform: str, limit: int = 50):
    agg = get_aggregator()
    return {"messages": agg.get_platform_messages(str(tenant_id), platform, limit)}


@router.post("/chat/reply")
async def send_reply(req: ChatReply):
    agg = get_aggregator()
    msg = agg.send_reply(str(req.tenant_id), req.platform, req.recipient, req.content)
    return msg
