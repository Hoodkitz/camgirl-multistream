"""Token-Bucket (Spec Kap. 10.1). In-Memory; Redis-LUA-Variante fuer Mehrknotenbetrieb."""
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    capacity: int
    refill_per_sec: float
    _state: dict[str, tuple[float, float]] = field(default_factory=dict)

    def take(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Gibt (erlaubt, retry_after_sekunden) zurueck."""
        now = time.monotonic() if now is None else now
        tokens, last = self._state.get(key, (float(self.capacity), now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill_per_sec)
        if tokens >= 1:
            self._state[key] = (tokens - 1, now)
            return True, 0.0
        self._state[key] = (tokens, now)
        return False, (1 - tokens) / self.refill_per_sec
