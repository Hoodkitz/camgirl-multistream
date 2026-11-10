"""Statistics endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone
from apps.api.schemas.stats import StreamStatsResponse
from apps.db.session import get_session
from apps.db.models import StreamSession as StreamSessionModel
from apps.api.security import require_role

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/stream/{stream_id}")
async def get_stream_stats(stream_id: UUID, session: AsyncSession = Depends(get_session), current_user: dict = Depends(require_role("model"))):
    stmt = select(StreamSessionModel).where(StreamSessionModel.id == stream_id)
    db = (await session.execute(stmt)).scalars().first()
    from fastapi import HTTPException
    if not db:
        raise HTTPException(status_code=404, detail="Stream not found")
    if current_user.get("tenant_id") and str(db.tenant_id) != current_user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    return StreamStatsResponse(
        stream_id=stream_id,
        viewer_count=db.viewer_count,
        duration_seconds=int((datetime.now(timezone.utc).replace(tzinfo=None) - db.started_at).total_seconds()),
        target_platforms=db.target_platforms,
        started_at=db.started_at,
        ended_at=db.ended_at,
    )


@router.get("/tenant/{tenant_id}/overview")
async def get_tenant_stats(tenant_id: UUID, session: AsyncSession = Depends(get_session), current_user: dict = Depends(require_role("model"))):
    from fastapi import HTTPException
    if current_user.get("tenant_id") and str(tenant_id) != current_user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
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
