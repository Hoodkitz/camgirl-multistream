"""Statistics endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timedelta
from ..schemas.stats import StatsResponse
from ...db.session import get_session
from ...db.models import StreamSession as StreamSessionModel

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/stream/{stream_id}")
async def get_stream_stats(stream_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(StreamSessionModel).where(StreamSessionModel.id == stream_id)
    db = (await session.execute(stmt)).scalars().first()
    if not db:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Stream not found")
    return StatsResponse(
        stream_id=stream_id,
        viewer_count=db.viewer_count,
        duration_seconds=int((datetime.utcnow() - db.started_at).total_seconds()),
        target_platforms=db.target_platforms,
        started_at=db.started_at,
        ended_at=db.ended_at,
    )


@router.get("/tenant/{tenant_id}/overview")
async def get_tenant_stats(tenant_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(StreamSessionModel).where(StreamSessionModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    sessions = result.scalars().all()
    
    active = sum(1 for s in sessions if s.is_active)
    total_viewers = sum(s.viewer_count for s in sessions)
    total_streams = len(sessions)
    
    return {
        "tenant_id": tenant_id,
        "active_streams": active,
        "total_viewers": total_viewers,
        "total_streams": total_streams,
        "sessions": [{"id": str(s.id), "is_active": s.is_active, "viewer_count": s.viewer_count} for s in sessions],
    }
