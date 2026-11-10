"""Stream management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
from apps.api.schemas.streams import (
    StreamCreate, StreamResponse, StreamSessionCreate, StreamSessionResponse
)
from apps.db.session import get_session
from apps.db.models import (
    StreamSession as StreamSessionModel, PlatformAccount as PlatformAccountModel,
    Tenant as TenantModel
)
from apps.services.stream_aggregator import StreamAggregator, get_stream_aggregator

router = APIRouter(prefix="/streams", tags=["streams"])


@router.post("", response_model=StreamResponse)
async def create_stream(req: StreamCreate, session: AsyncSession = Depends(get_session)):
    # Validate tenant
    stmt = select(TenantModel).where(TenantModel.id == req.tenant_id)
    tenant = (await session.execute(stmt)).scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not req.target_platforms:
        raise HTTPException(status_code=400, detail="At least one target platform required")
    
    db_session = StreamSessionModel(
        id=UUID(str(req.tenant_id) + "_session_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")),
        tenant_id=req.tenant_id,
        ingest_protocol=req.ingest_protocol,
        target_platforms=req.target_platforms,
    )
    session.add(db_session)
    await session.commit()
    return db_session


@router.get("/{session_id}", response_model=StreamResponse)
async def get_stream(session_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(StreamSessionModel).where(StreamSessionModel.id == session_id)
    db_session = (await session.execute(stmt)).scalars().first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Stream session not found")
    return db_session


@router.get("/active")
async def get_active_streams(session: AsyncSession = Depends(get_session)):
    from datetime import datetime
    stmt = select(StreamSessionModel).where(StreamSessionModel.is_active == True)
    result = await session.execute(stmt)
    return [s async for s in result.scalars]


@router.post("/{session_id}/trigger")
async def trigger_stream(session_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(StreamSessionModel).where(StreamSessionModel.id == session_id)
    db_session = (await session.execute(stmt)).scalars().first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    aggregator = await get_stream_aggregator()
    result = await aggregator.trigger_stream(str(db_session.id), db_session.target_platforms)
    db_session.is_active = True
    db_session.viewer_count = result.get("viewer_count", 0)
    await session.commit()
    return result


@router.post("/{session_id}/stop")
async def stop_stream(session_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(StreamSessionModel).where(StreamSessionModel.id == session_id)
    db_session = (await session.execute(stmt)).scalars().first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Stream not found")
    db_session.is_active = False
    db_session.ended_at = datetime.utcnow()
    await session.commit()
    return {"status": "stopped", "id": session_id}


@router.get("/{session_id}/stats")
async def get_stream_stats(session_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(StreamSessionModel).where(StreamSessionModel.id == session_id)
    db_session = (await session.execute(stmt)).scalars().first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Stream not found")
    return db_session.stats
