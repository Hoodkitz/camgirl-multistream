"""Outbox-Worker mit Exponential Backoff + Jitter (Spec Kap. 9.2)."""
import json
import logging
import random
import uuid
from datetime import timedelta

import httpx
from sqlalchemy import select

from apps.core.config import settings
from apps.db.models import ChatEvent, Outbox, PlatformAccount, Tenant, utcnow
from apps.db.session import SystemSessionLocal as SessionLocal
from apps.domain.signing import sign
from apps.domain.vault import Sealed, unseal
from apps.services import connectors
from apps.services.bus import bus
from apps.services.events import event_dict
from apps.services.kms import kms_for

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 8


def backoff(attempt: int) -> timedelta:
    base = min(2 ** attempt, 3600)
    return timedelta(seconds=base * (0.5 + random.random()))


async def _chat_reply(db, e: Outbox) -> None:
    p = e.payload
    tenant = await db.get(Tenant, e.tenant_id)
    acc = (await db.execute(select(PlatformAccount).where(
        PlatformAccount.tenant_id == e.tenant_id, PlatformAccount.platform == p["platform"],
        PlatformAccount.enabled.is_(True)))).scalars().first()
    if acc is None:
        raise RuntimeError(f"Kein aktives Konto fuer {p['platform']}")
    creds = unseal(kms_for(tenant), acc.kek_ref, str(e.tenant_id), acc.platform,
                   Sealed(acc.encrypted_credentials, acc.wrapped_dek, acc.iv, acc.auth_tag))
    await connectors.connector.send(acc.platform, acc.account_username, creds, p.get("recipient"), p["text"])
    row = ChatEvent(tenant_id=e.tenant_id, event_id=f"out_{e.id}", platform=acc.platform, event_type="message",
                    ts=utcnow(), sender_name=acc.account_username, message=p["text"], is_outgoing=True,
                    is_automated=bool(p.get("automated")))
    db.add(row)
    await db.flush()
    bus.publish(str(e.tenant_id), {"type": "chat_event", "event": event_dict(row), "actions": []})


async def _obs_webhook(e: Outbox) -> None:
    from urllib.parse import urlsplit

    from apps.domain.netguard import assert_public_host
    u = urlsplit(e.payload["url"])
    if u.scheme != "https":
        raise RuntimeError("OBS-Webhook muss https sein")
    assert_public_host(u.hostname or "", u.port or 443)  # beim Senden erneut pruefen (DNS-Rebinding)
    body = json.dumps({k: v for k, v in e.payload.items() if k != "url"}).encode()
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        r = await client.post(e.payload["url"], content=body, headers={
            "Content-Type": "application/json", "X-Signature": sign(settings.OBS_WEBHOOK_SECRET, body)})
        r.raise_for_status()


async def process(tenant_id: uuid.UUID | None = None, limit: int = 50) -> int:
    done = 0
    async with SessionLocal() as db:
        q = select(Outbox).where(Outbox.status == "PENDING", Outbox.next_attempt_at <= utcnow())
        if tenant_id:
            q = q.where(Outbox.tenant_id == tenant_id)
        if db.bind.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        for e in (await db.execute(q.order_by(Outbox.created_at).limit(limit))).scalars().all():
            try:
                if e.kind == "chat_reply":
                    await _chat_reply(db, e)
                elif e.kind == "obs_webhook":
                    await _obs_webhook(e)
                else:
                    raise RuntimeError(f"Unbekannter Outbox-Typ {e.kind}")
                e.status = "DONE"
                done += 1
            except Exception as ex:
                e.attempts += 1
                e.last_error = str(ex)[:500]
                e.status = "DEAD" if e.attempts >= MAX_ATTEMPTS else "PENDING"
                e.next_attempt_at = utcnow() + backoff(e.attempts)
                log.warning("Outbox %s Versuch %s fehlgeschlagen: %s", e.id, e.attempts, ex)
        await db.commit()
    return done
