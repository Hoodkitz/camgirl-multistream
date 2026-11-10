"""Chat aggregation service for multi-platform chat bundling."""
import asyncio
import httpx
from typing import Dict, List
from datetime import datetime
from apps.core.config import settings
import redis.asyncio as redis


class ChatAggregator:
    def __init__(self):
        self._messages: Dict[str, List[dict]] = {}
        self._platforms: Dict[str, str] = {}
        self._r = None

    async def connect_redis(self):
        if self._r is None:
            self._r = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    def register_platform(self, tenant_id: str, platform: str, account_id: str):
        self._platforms[f"{tenant_id}:{platform}"] = account_id

    async def ingest_message(self, tenant_id: str, platform: str, sender: str, content: str, msg_type: str = "message") -> dict:
        """Ingest a message from any platform."""
        await self.connect_redis()
        
        msg = {
            "id": f"{tenant_id}:{platform}:{datetime.utcnow().timestamp()}",
            "tenant_id": tenant_id,
            "platform": platform,
            "sender": sender,
            "content": content,
            "type": msg_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        key = f"chat:{tenant_id}"
        await self._r.sadd(key, msg["id"])
        
        self._messages.setdefault(tenant_id, []).append(msg)
        
        # Notify connected WebSocket clients
        await self._r.publish("chat:events", json.dumps({
            "type": "message",
            "message": msg,
        }))
        
        return msg

    def get_unified_inbox(self, tenant_id: str, limit: int = 50) -> List[dict]:
        """Get unified inbox across all platforms."""
        msgs = sorted(self._messages.get(tenant_id, []), key=lambda m: m["timestamp"], reverse=True)
        return msgs[:limit]

    def get_platform_messages(self, tenant_id: str, platform: str, limit: int = 50) -> List[dict]:
        """Get messages from a specific platform."""
        msgs = [m for m in self._messages.get(tenant_id, []) if m["platform"] == platform]
        return sorted(msgs, key=lambda m: m["timestamp"], reverse=True)[:limit]

    def send_reply(self, tenant_id: str, platform: str, recipient: str, content: str) -> dict:
        """Send a reply to a specific platform."""
        msg = {
            "id": f"{tenant_id}:{platform}:reply:{datetime.utcnow().timestamp()}",
            "tenant_id": tenant_id,
            "platform": platform,
            "sender": "model",
            "recipient": recipient,
            "content": content,
            "type": "reply",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._messages.setdefault(tenant_id, []).append(msg)
        return msg

    def generate_auto_response(self, tenant_id: str, platform: str, sender: str, content: str) -> str:
        """Generate an auto-response based on platform and sender."""
        # Simple template-based response
        if "new" in content.lower()[:50]:
            return f"Hallo {sender}! Willkommen auf dem Stream. Schaut gerne vorbei!"
        elif len(content) > 100:
            return f"Danke für deine Nachricht {sender}! Ich schaue mir das gerne an."
        else:
            return f"OK {sender}! Bei Bedarf melde dich gerne."


class ChatAggregatorManager:
    _instance = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = ChatAggregator()
        return cls._instance


async def get_chat_aggregator():
    return await ChatAggregatorManager.get_instance()
