"""Stream aggregation service - directs RTMP/SRT stream to all portals."""
import asyncio
import aiohttp
import json
from typing import Dict, List
from datetime import datetime
from ..core.config import settings
import redis.asyncio as redis


class StreamAggregator:
    def __init__(self):
        self._streams: Dict[str, dict] = {}
        self._r = None

    async def connect_redis(self):
        if self._r is None:
            self._r = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    async def trigger_stream(self, stream_id: str, target_platforms: List[str]) -> dict:
        """Trigger streaming to all target platforms."""
        await self.connect_redis()
        
        config = {
            "stream_id": stream_id,
            "started_at": datetime.utcnow().isoformat(),
            "target_platforms": target_platforms,
            "config": {
                "ingest_url": f"rtmp://localhost:1935/live/stream{stream_id}",
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
            "start_time": datetime.utcnow(),
            "is_active": True,
            "platforms": target_platforms,
            "viewers": 0,
        }
        
        return {
            "stream_id": stream_id,
            "status": "active",
            "platforms_activated": target_platforms,
            "start_time": config["started_at"],
            "viewer_count": 0,
            "ingest_url": config["config"]["ingest_url"],
        }

    async def stop_stream(self, stream_id: str) -> dict:
        """Stop streaming."""
        if stream_id in self._streams:
            del self._streams[stream_id]
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
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = StreamAggregator()
        return cls._instance


async def get_stream_aggregator():
    return await StreamAggregatorManager.get_instance()
