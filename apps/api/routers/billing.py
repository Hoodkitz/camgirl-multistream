"""Stripe Checkout + customer portal. The tier itself is only ever set by the signed webhook (system router)."""
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.core.config import settings
from apps.core.enums import Tier
from apps.core.permissions import Permission as P
from apps.db import models as m
from apps.security.auth import CurrentUser, get_db, require

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
STRIPE = "https://api.stripe.com/v1"


class CheckoutIn(BaseModel):
    tier: Tier


def _prices() -> dict[Tier, str]:
    return {Tier.PRO: settings.STRIPE_PRICE_PRO, Tier.AGENCY: settings.STRIPE_PRICE_AGENCY}


async def _stripe(path: str, form: list[tuple[str, str]]) -> dict:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(503, "Zahlungen sind noch nicht eingerichtet")
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{STRIPE}/{path}", content=urlencode(form),
                             headers={"Content-Type": "application/x-www-form-urlencoded"},
                             auth=(settings.STRIPE_SECRET_KEY, ""))
    except httpx.HTTPError:
        raise HTTPException(502, "Zahlungsanbieter nicht erreichbar")
    if r.status_code >= 400:
        raise HTTPException(502, "Zahlungsanbieter hat die Anfrage abgelehnt")
    return r.json()


@router.post("/checkout")
async def checkout(req: CheckoutIn, user: CurrentUser = Depends(require(P.TENANT_DELETE)), db=Depends(get_db)):
    price = _prices().get(req.tier)
    if not price:
        raise HTTPException(422, "Für diesen Tarif gibt es keinen Preis")
    t = await db.get(m.Tenant, user.tenant_id)
    if t is None:
        raise HTTPException(404, "Mandant nicht gefunden")
    if t.stripe_customer_id and t.tier != Tier.STANDARD.value:
        raise HTTPException(409, "Es besteht bereits ein Abo – Tarifwechsel bitte über das Kundenportal")
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    form = [("mode", "subscription"), ("line_items[0][price]", price), ("line_items[0][quantity]", "1"),
            ("success_url", f"{base}/app/?billing=success"), ("cancel_url", f"{base}/app/?billing=cancel"),
            ("client_reference_id", str(t.id)), ("allow_promotion_codes", "true"),
            ("subscription_data[metadata][tenant_id]", str(t.id)),
            ("subscription_data[metadata][tier]", req.tier.value)]
    if t.stripe_customer_id:
        form.append(("customer", t.stripe_customer_id))
    session = await _stripe("checkout/sessions", form)
    return {"url": session["url"]}


@router.post("/portal")
async def portal(user: CurrentUser = Depends(require(P.TENANT_DELETE)), db=Depends(get_db)):
    t = await db.get(m.Tenant, user.tenant_id)
    if t is None or not t.stripe_customer_id:
        raise HTTPException(404, "Noch kein Abo vorhanden")
    session = await _stripe("billing_portal/sessions", [("customer", t.stripe_customer_id),
                                                         ("return_url", f"{settings.PUBLIC_BASE_URL.rstrip('/')}/app/")])
    return {"url": session["url"]}


async def cancel_all_subscriptions(customer: str) -> None:
    """Cancel every live subscription of the customer immediately; raises 502 if Stripe refuses (deletion aborts)."""
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(503, "Abo kann nicht gekündigt werden (Zahlungen nicht eingerichtet) – Löschung abgebrochen")
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{STRIPE}/subscriptions", auth=(settings.STRIPE_SECRET_KEY, ""),
                            params={"customer": customer, "status": "all", "limit": 100})
            r.raise_for_status()
            for sub in r.json().get("data", []):
                if sub.get("status") not in ("canceled", "incomplete_expired"):
                    d = await c.delete(f"{STRIPE}/subscriptions/{sub['id']}", auth=(settings.STRIPE_SECRET_KEY, ""))
                    d.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "Abo konnte nicht gekündigt werden – Löschung abgebrochen, bitte erneut versuchen")
