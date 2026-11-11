"""Token-Bucket (Spec Kap. 10.1). In-Memory; Redis-LUA-Variante fuer Mehrknotenbetrieb."""
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    capacity: int
    refill_per_sec: float
    _state: dict[str, tuple[float, float]] = field(default_factory=dict)

    max_keys: int = 50_000

    def _prune(self, now: float) -> None:
        """Drop buckets that have refilled completely: they carry no state worth keeping (bounded memory)."""
        full_after = self.capacity / self.refill_per_sec
        for k, (_, last) in list(self._state.items()):
            if now - last >= full_after:
                del self._state[k]
        if len(self._state) >= self.max_keys:  # still too many: drop the oldest half
            for k, _ in sorted(self._state.items(), key=lambda kv: kv[1][1])[: len(self._state) // 2]:
                del self._state[k]

    def take(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Gibt (erlaubt, retry_after_sekunden) zurueck."""
        now = time.monotonic() if now is None else now
        if key not in self._state and len(self._state) >= self.max_keys:
            self._prune(now)
        tokens, last = self._state.get(key, (float(self.capacity), now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill_per_sec)
        if tokens >= 1:
            self._state[key] = (tokens - 1, now)
            return True, 0.0
        self._state[key] = (tokens, now)
        return False, (1 - tokens) / self.refill_per_sec
