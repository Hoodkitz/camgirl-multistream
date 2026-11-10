"""Chat aggregation service for multi-platform chat."""
from typing import Dict, List
from datetime import datetime
from collections import defaultdict


class ChatAggregator:
    def __init__(self):
        self._messages: Dict[str, List[dict]] = defaultdict(list)
        self._platforms: Dict[str, str] = {}

    def register_platform(self, tenant_id: str, platform: str, account_id: str):
        self._platforms[f"{tenant_id}:{platform}"] = account_id

    def ingest_message(self, tenant_id: str, platform: str, sender: str, content: str, msg_type: str = "message"):
        msg = {
            "id": f"{tenant_id}:{platform}:{datetime.utcnow().timestamp()}",
            "tenant_id": tenant_id,
            "platform": platform,
            "sender": sender,
            "content": content,
            "type": msg_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._messages[tenant_id].append(msg)
        return msg

    def get_unified_inbox(self, tenant_id: str, limit: int = 50) -> List[dict]:
        msgs = sorted(self._messages.get(tenant_id, []), key=lambda m: m["timestamp"], reverse=True)
        return msgs[:limit]

    def get_platform_messages(self, tenant_id: str, platform: str, limit: int = 50) -> List[dict]:
        msgs = [m for m in self._messages.get(tenant_id, []) if m["platform"] == platform]
        return sorted(msgs, key=lambda m: m["timestamp"], reverse=True)[:limit]

    def send_reply(self, tenant_id: str, platform: str, recipient: str, content: str) -> dict:
        msg = self.ingest_message(tenant_id, platform, "model", content, "reply")
        msg["recipient"] = recipient
        return msg
