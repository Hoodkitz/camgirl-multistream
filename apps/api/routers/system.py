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


async def _customer_tier(customer: str | None) -> Tier | None:
    """Best tier over ALL active subscriptions of the customer (None = could not ask Stripe)."""
    if not customer or not settings.STRIPE_SECRET_KEY:
        return None
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.stripe.com/v1/subscriptions", auth=(settings.STRIPE_SECRET_KEY, ""),
                            params={"customer": customer, "status": "all", "limit": 20})
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    best = Tier.STANDARD
    for sub in r.json().get("data", []):
        if sub.get("status") in ("active", "trialing"):
            t = _tier_from_prices(sub)
            if t == Tier.AGENCY or (t == Tier.PRO and best == Tier.STANDARD):
                best = t
    return best


async def process_inbox() -> int:
    """Each event is handled and committed on its own: one malformed event can never block the others."""
    import uuid
    n = 0
    async with SessionLocal() as db:
        ids = (await db.execute(select(WebhookInbox.event_id).where(WebhookInbox.processed_at.is_(None))
                                .order_by(WebhookInbox.received_at))).scalars().all()
    for wid in ids:
        async with SessionLocal() as db:
            w = await db.get(WebhookInbox, wid)
            if w is None or w.processed_at is not None:
                continue
            try:
                obj = (w.payload.get("data") or {}).get("object") or {}
                meta = obj.get("metadata") or {}
                etype = w.payload.get("type")
                if etype in ("customer.subscription.created", "customer.subscription.updated",
                             "customer.subscription.deleted") and meta.get("tenant_id"):
                    t = await db.get(Tenant, uuid.UUID(str(meta["tenant_id"])))
                    created = int(w.payload.get("created") or 0)
                    if t and created < (t.billing_event_at or 0):
                        t = None  # older than the state already applied (Stripe does not guarantee ordering)
                    if t:
                        t.billing_event_at = created
                        t.stripe_customer_id = obj.get("customer") or t.stripe_customer_id
                        tier = await _customer_tier(t.stripe_customer_id)  # all subscriptions, not just this one
                        if tier is None:  # Stripe not reachable/configured: fall back to this event
                            active = obj.get("status") in ("active", "trialing") and etype != "customer.subscription.deleted"
                            this = _tier_from_prices(obj)  # never trust metadata
                            tier = this if active and this else Tier.STANDARD
                        t.tier = tier.value
            except (ValueError, TypeError, AttributeError) as e:  # malformed event: record, never retry forever
                w.payload = {**w.payload, "_error": f"{type(e).__name__}"}
            w.processed_at = utcnow()
            await db.commit()
            n += 1
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
