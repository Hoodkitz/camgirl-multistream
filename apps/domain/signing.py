"""HMAC-Signaturen fuer Webhooks (Stripe-kompatibles Schema, OBS-Outbox)."""
import hashlib
import hmac
import time


def sign(secret: str, body: bytes, ts: int | None = None) -> str:
    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(secret: str, body: bytes, header: str, tolerance: int = 300, now: int | None = None) -> bool:
    try:
        pairs = [p.split("=", 1) for p in header.split(",") if "=" in p]
        ts = int(dict(pairs)["t"])
        given = [v for k, v in pairs if k == "v1"]  # several during a secret rotation: any may match
    except (ValueError, KeyError):
        return False
    if not given:
        return False
    now = int(time.time()) if now is None else now
    if abs(now - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, g) for g in given)
