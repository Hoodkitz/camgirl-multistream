"""System-Endpunkte: Stripe-Webhook (Inbox), Outbox-Trigger, Retention."""
import json
from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from apps.core.config import settings
from apps.core.enums import Tier
from apps.db.models import ChatEvent, Tenant, WebhookInbox, utcnow
from apps.db.session import SystemSessionLocal as SessionLocal
from apps.domain.signing import verify
from apps.security.auth import require_secret
from apps.services import outbox

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, sig: str | None = Header(None, alias="Stripe-Signature")):
    body = await request.body()
    if not sig or not verify(settings.STRIPE_WEBHOOK_SECRET, body, sig):
        raise HTTPException(400, "Ungueltige Signatur")
    event = json.loads(body)
    async with SessionLocal() as db:
        db.add(WebhookInbox(event_id=event["id"], source="stripe", payload=event))
        try:
            await db.commit()
        except IntegrityError:
            return {"status": "duplicate"}  # idempotent: 200 OK
    await process_inbox()
    return {"status": "accepted"}


def _tier_from_prices(sub: dict) -> Tier | None:
    """Tier = highest plan whose configured Stripe price id is part of the subscription."""
    by_price = {settings.STRIPE_PRICE_AGENCY: Tier.AGENCY, settings.STRIPE_PRICE_PRO: Tier.PRO}
    found = set()
    for item in (sub.get("items") or {}).get("data", []) or []:
        price = (item.get("price") or {}).get("id")
        if price and price in by_price:
            found.add(by_price[price])
    for tier in (Tier.AGENCY, Tier.PRO):
        if tier in found:
            return tier
    return None


async def process_inbox() -> int:
    n = 0
    async with SessionLocal() as db:
        rows = (await db.execute(select(WebhookInbox).where(WebhookInbox.processed_at.is_(None)))).scalars().all()
        for w in rows:
            obj = w.payload.get("data", {}).get("object", {})
            meta = obj.get("metadata", {}) or {}
            if w.payload.get("type") in ("customer.subscription.created", "customer.subscription.updated",
                                         "customer.subscription.deleted") and meta.get("tenant_id"):
                import uuid
                t = await db.get(Tenant, uuid.UUID(meta["tenant_id"]))
                created = int(w.payload.get("created") or 0)
                if t and created < (t.billing_event_at or 0):
                    t = None  # older than the state already applied (Stripe does not guarantee ordering)
                if t:
                    t.billing_event_at = created
                    active = obj.get("status") in ("active", "trialing") and w.payload["type"] != "customer.subscription.deleted"
                    tier = _tier_from_prices(obj)  # never trust metadata: plan switches in the portal keep old metadata
                    t.tier = tier.value if active and tier else Tier.STANDARD.value
                    t.stripe_customer_id = obj.get("customer")
            w.processed_at = utcnow()
            n += 1
        await db.commit()
    return n


@router.post("/outbox/trigger")
async def outbox_trigger(secret: str | None = Header(None, alias="X-Worker-Secret")):
    require_secret(secret, settings.CONNECTOR_SECRET)
    return {"processed": await outbox.process()}


@router.post("/maintenance/retention")
async def retention(secret: str | None = Header(None, alias="X-Worker-Secret")):
    """Chat-Protokolle physisch nach 30 Tagen loeschen; Tip-Events bleiben (Aufbewahrungspflicht)."""
    require_secret(secret, settings.CONNECTOR_SECRET)
    cutoff = utcnow() - timedelta(days=settings.CHAT_RETENTION_DAYS)
    async with SessionLocal() as db:
        res = await db.execute(delete(ChatEvent).where(ChatEvent.ts < cutoff, ChatEvent.event_type != "tip"))
        # Bei Tips bleibt nur der Buchungsteil; Nachrichtentext wird entfernt
        old_tips = (await db.execute(select(ChatEvent).where(ChatEvent.ts < cutoff, ChatEvent.event_type == "tip",
                                                             ChatEvent.message.is_not(None)))).scalars().all()
        for t in old_tips:
            t.message = None
        await db.commit()
    return {"geloescht": res.rowcount, "tips_anonymisiert": len(old_tips)}
