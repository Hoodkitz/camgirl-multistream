"""API Key Manager for securing platform API access."""
import secrets
from datetime import datetime, timedelta
from typing import Dict
from apps.core.config import settings
import redis.asyncio as redis


class APIKeyManager:
    def __init__(self):
        self._keys: Dict[str, dict] = {}
        self._r = None

    async def connect_redis(self):
        if self._r is None:
            self._r = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    async def generate_key(self, tenant_id: str, platform: str) -> str:
        """Generate a new API key for a platform."""
        await self.connect_redis()
        key = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        self._keys[key] = {
            "tenant_id": tenant_id,
            "platform": platform,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "is_active": True,
        }
        await self._r.set(f"apikey:{key}", "active")
        return key

    async def validate_key(self, key: str) -> dict | None:
        """Validate an API key."""
        if key in self._keys:
            return self._keys[key]
        return None


class APIKeyManagerManager:
    _instance = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = APIKeyManager()
        return cls._instance


async def get_api_key_manager():
    return await APIKeyManagerManager.get_instance()
