"""Chat aggregation service for multi-platform chat bundling."""
import asyncio
import httpx
import json
from typing import Dict, List, Optional
from datetime import datetime, timezone
from apps.core.config import settings
import redis.asyncio as redis
from apps.services.chat_adapter import ChaturbateChatAdapter
from apps.db.models import PlatformAccount as PlatformAccountModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from apps.services.credentials_manager import CredentialsManager


class ChatAggregator:
    def __init__(self, adapters=None):
        self._messages: Dict[str, List[dict]] = {}
        self._platforms: Dict[str, str] = {}
        self._r = None
        self._adapters = adapters if adapters is not None else {
            "chaturbate": ChaturbateChatAdapter(),
            # other adapters would be instantiated here for production
        }
        self._cred_manager = CredentialsManager()

    async def connect_redis(self):
        if self._r is None:
            self._r = await redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    def register_platform(self, tenant_id: str, platform: str, account_id: str):
        self._platforms[f"{tenant_id}:{platform}"] = account_id

    async def ingest_message(self, tenant_id: str, platform: str, sender: str, content: str, msg_type: str = "message") -> dict:
        """Ingest a message from any platform."""
        await self.connect_redis()
        
        msg = {
            "id": f"{tenant_id}:{platform}:{datetime.now(timezone.utc).timestamp()}",
            "tenant_id": tenant_id,
            "platform": platform,
            "sender": sender,
            "content": content,
            "type": msg_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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

    async def send_reply(self, tenant_id: str, platform: str, recipient: str, content: str, db_session: Optional[AsyncSession] = None) -> dict:
        """Send a reply to a specific platform."""
        credentials = {}
        if db_session:
            stmt = select(PlatformAccountModel).where(
                PlatformAccountModel.tenant_id == tenant_id,
                PlatformAccountModel.platform_name == platform
            )
            result = await db_session.execute(stmt)
            account = result.scalars().first()
            if account:
                # We expect the actual credential, decrypted
                credentials = {"api_key": self._cred_manager.decrypt(account.encrypted_credentials)}

        adapter = self._adapters.get(platform)
        if adapter:
            success = await adapter.send_message(credentials, recipient, content)
            if not success:
                print(f"Failed to send message via adapter for {platform}")

        msg = {
            "id": f"{tenant_id}:{platform}:reply:{datetime.now(timezone.utc).timestamp()}",
            "tenant_id": tenant_id,
            "platform": platform,
            "sender": "model",
            "recipient": recipient,
            "content": content,
            "type": "reply",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    async def get_instance(cls, adapters=None):
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = ChatAggregator(adapters=adapters)
        return cls._instance


async def get_chat_aggregator(adapters=None):
    return await ChatAggregatorManager.get_instance(adapters)
