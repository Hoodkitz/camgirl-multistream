"""Event-Bus zu den WebSocket-Clients (Spec Kap. 5.2/5.3).

In-Memory Pub/Sub pro Mandant. Fuer Mehrknotenbetrieb durch Redis Streams/PubSub
ersetzbar (gleiche Schnittstelle). Replay nach Reconnect erfolgt ueber die DB (`since`).
"""
import asyncio
from collections import defaultdict


class EventBus:
    def __init__(self, max_queue: int = 1000):
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._max = max_queue

    def subscribe(self, tenant_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self._max)
        self._subs[tenant_id].add(q)
        return q

    def unsubscribe(self, tenant_id: str, q: asyncio.Queue) -> None:
        self._subs[tenant_id].discard(q)

    def publish(self, tenant_id: str, event: dict) -> int:
        delivered = 0
        for q in list(self._subs.get(tenant_id, ())):
            try:
                q.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:  # langsamer Client: aelteste Nachricht verwerfen, Replay via DB
                q.get_nowait()
                q.put_nowait(event)
        return delivered

    def subscriber_count(self, tenant_id: str) -> int:
        return len(self._subs.get(tenant_id, ()))


bus = EventBus()
