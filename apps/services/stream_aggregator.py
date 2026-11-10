"""Stream aggregation service - directs RTMP/SRT stream to all portals."""
import asyncio
import aiohttp
import json
from apps.services.stream_adapter import FfmpegStreamAdapter, StreamAdapter
from typing import Dict, List
from datetime import datetime, timezone
from apps.core.config import settings
import redis.asyncio as redis
from apps.db.models import PlatformAccount as PlatformAccountModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from apps.services.credentials_manager import CredentialsManager

class StreamAggregator:
    def __init__(self, adapter: StreamAdapter = None):
        self._streams: Dict[str, dict] = {}
        self._r = None
        # Use real ffmpeg adapter in production
        self._adapter = adapter if adapter is not None else FfmpegStreamAdapter()
        self._cred_manager = CredentialsManager()

    async def connect_redis(self):
        if self._r is None:
            self._r = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    async def trigger_stream(self, stream_id: str, tenant_id: str, target_platforms: List[str], db_session: AsyncSession) -> dict:
        """Trigger streaming to all target platforms using actual credentials."""
        await self.connect_redis()
        
        # Fetch real credentials for tenant and requested platforms
        stmt = select(PlatformAccountModel).where(
            PlatformAccountModel.tenant_id == tenant_id,
            PlatformAccountModel.platform_name.in_(target_platforms)
        )
        result = await db_session.execute(stmt)
        accounts = result.scalars().all()

        output_urls = []
        platforms_activated = []
        for account in accounts:
            stream_key = self._cred_manager.decrypt(account.encrypted_credentials)
            # In a real app, URL format depends on platform. Simplified here.
            base_url = f"rtmp://{account.platform_name}.example.com/live"
            output_urls.append(f"{base_url}/{stream_key}")
            platforms_activated.append(account.platform_name)

        ingest_url = f"rtmp://localhost:1935/live/stream{stream_id}"

        # Start streaming via adapter
        if output_urls:
            self._adapter.start_stream(ingest_url, output_urls)

        config = {
            "stream_id": stream_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "target_platforms": target_platforms,
            "config": {
                "ingest_url": ingest_url,
                "srt_url": f"srt://localhost:8888?mode=rsub&pass=async:1",
            }
        }
        
        # Publish to Redis stream for streaming workers
        await self._r.xadd("stream:trigger", {
            "trigger_type": "start",
            "data": json.dumps(config),
        })
        
        self._streams[stream_id] = {
            "stream_id": stream_id,
            "start_time": datetime.now(timezone.utc),
            "is_active": True,
            "platforms": target_platforms,
            "viewers": 0,
        }
        
        return {
            "stream_id": stream_id,
            "status": "active",
            "platforms_activated": platforms_activated,
            "start_time": config["started_at"],
            "viewer_count": 0,
            "ingest_url": config["config"]["ingest_url"],
        }

    async def stop_stream(self, stream_id: str) -> dict:
        """Stop streaming."""
        ingest_url = f"rtmp://localhost:1935/live/stream{stream_id}"
        self._adapter.stop_stream(ingest_url)

        if stream_id in self._streams:
            del self._streams[stream_id]

        # Make sure Redis connection exists
        await self.connect_redis()

        await self._r.xadd("stream:trigger", {
            "trigger_type": "stop",
            "stream_id": stream_id,
        })
        return {"status": "stopped", "stream_id": stream_id}

    async def update_viewers(self, stream_id: str, count: int):
        """Update viewer count."""
        if stream_id in self._streams:
            self._streams[stream_id]["viewers"] = count

class StreamAggregatorManager:
    _instance = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, adapter=None):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = StreamAggregator(adapter=adapter)
        return cls._instance

async def get_stream_aggregator(adapter=None):
    return await StreamAggregatorManager.get_instance(adapter)
