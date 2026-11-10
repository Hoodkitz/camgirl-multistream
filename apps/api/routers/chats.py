"""Chat endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from apps.api.schemas.chats import (
    ChatIngest, ChatResponse, ChatMessageCreate, ChatMessageResponse
)
from apps.db.session import get_session
from apps.db.models import ChatMessage as ChatMessageModel
from apps.services.chat_aggregator import ChatAggregator, get_chat_aggregator

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("/ingest")
async def ingest_chat(req: ChatIngest, session: AsyncSession = Depends(get_session)):
    aggregator = await get_chat_aggregator()
    
    # Save to DB
    db_msg = ChatMessageModel(
        event_id=req.event_id[:255],
        tenant_id=req.tenant_id,
        stream_id=req.stream_id,
        platform=req.platform,
        event_type=req.event_type,
        timestamp=req.timestamp,
        sender=req.sender,
        payload=req.payload,
    )
    session.add(db_msg)
    await session.commit()
    
    # Also add to aggregator for unified inbox
    msg = aggregator.ingest_message(
        tenant_id=str(req.tenant_id),
        platform=req.platform,
        sender=req.sender,
        content=str(req.payload.get("content", "")),
        msg_type=req.event_type,
    )
    return {"status": "ingested", "message": msg}


@router.get("/inbox/{tenant_id}")
async def unified_inbox(tenant_id: UUID, limit: int = 50, session: AsyncSession = Depends(get_session)):
    aggregator = await get_chat_aggregator()
    
    # Get DB messages
    stmt = select(ChatMessageModel).where(ChatMessageModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    db_messages = result.scalars().all()
    
    # Get unified inbox from aggregator
    unified = aggregator.get_unified_inbox(tenant_id, limit)
    
    return {"unified_inbox": unified, "db_messages_count": len(db_messages)}


@router.get("/platform/{tenant_id}/{platform}")
async def platform_chats(tenant_id: UUID, platform: str, limit: int = 50, session: AsyncSession = Depends(get_session)):
    aggregator = await get_chat_aggregator()
    msgs = aggregator.get_platform_messages(tenant_id, platform, limit)
    return {"platform": platform, "messages": msgs}


@router.post("/reply")
async def send_reply(req: ChatResponse, session: AsyncSession = Depends(get_session)):
    aggregator = await get_chat_aggregator()
    msg = aggregator.send_reply(
        tenant_id=str(req.tenant_id),
        platform=req.platform,
        recipient=req.recipient,
        content=req.content,
    )
    return {"status": "sent", "message": msg}


@router.post("/auto-respond")
async def auto_respond(req: ChatResponse, session: AsyncSession = Depends(get_session)):
    aggregator = await get_chat_aggregator()
    # Simulate AI auto-response
    response = aggregator.generate_auto_response(
        tenant_id=str(req.tenant_id),
        platform=req.platform,
        sender=req.sender,
        content=req.content,
    )
    return {"auto_response": response, "is_automated": True}
