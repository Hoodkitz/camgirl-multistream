"""Stream management endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["streams"])


class StreamStartRequest(BaseModel):
    tenant_id: UUID
    platforms: List[str]
    ingest_protocol: str = "rtmp"


@router.post("/streams/start")
async def start_stream(req: StreamStartRequest):
    return {"stream_id": str(UUID(int=1)), "ingest_url": "rtmp://localhost:1935/live", "status": "active"}


@router.post("/streams/{stream_id}/stop")
async def stop_stream(stream_id: UUID):
    return {"stream_id": str(stream_id), "status": "stopped"}


@router.get("/streams/{stream_id}/status")
async def stream_status(stream_id: UUID):
    return {"stream_id": str(stream_id), "is_active": True, "viewers": 0}
