"""Chat-Aggregation: Ingest (Connectors), Inbox, Antworten, WebSocket-Feed."""
import asyncio
import secrets
import time
import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas import PortalEvent, ReplyIn
from apps.core.config import settings
from apps.core.permissions import Permission as P
from apps.db.models import ChatEvent, Outbox, PlatformAccount, Tenant
from apps.db.session import SessionLocal, set_tenant_context
from apps.security.auth import CurrentUser, _check_account, get_db, require, require_secret
from apps.services import events as ev_svc, outbox
from apps.services.bus import bus

router = APIRouter(tags=["chat"])

# Kurzlebige WS-Tickets (Spec Kap. 8.2: Ticket-Auth via Query). Einmalig, 30s gueltig.
_tickets: dict[str, tuple[uuid.UUID, float]] = {}
TICKET_TTL = 30


@router.post("/api/v1/events", status_code=202)
async def ingest_event(ev: PortalEvent, secret: str | None = Header(None, alias="X-Connector-Secret")):
    require_secret(secret, settings.CONNECTOR_SECRET)
    async with SessionLocal() as db:
        await set_tenant_context(db, str(ev.tenant_id))
        if await db.get(Tenant, ev.tenant_id) is None:
            raise HTTPException(404, "Mandant unbekannt")
        row, actions = await ev_svc.ingest(db, ev.tenant_id, ev)
    if actions:
        await outbox.process(ev.tenant_id)
    return {"status": "duplicate" if row is None else "accepted", "actions": actions}


@router.get("/api/v1/chat/inbox")
async def inbox(platform: str | None = None, since_id: int | None = None, limit: int = 100,
                user: CurrentUser = Depends(require(P.CHAT_READ)), db: AsyncSession = Depends(get_db)):
    """Gebuendelter Posteingang; `since_id` fuer verlustfreien Replay nach Reconnect."""
    q = select(ChatEvent).where(ChatEvent.tenant_id == user.tenant_id)
    if platform:
        q = q.where(ChatEvent.platform == platform)
    if since_id is not None:
        q = q.where(ChatEvent.id > since_id).order_by(ChatEvent.id).limit(min(limit, 500))
        rows = (await db.execute(q)).scalars().all()
    else:
        rows = list(reversed((await db.execute(q.order_by(ChatEvent.id.desc()).limit(min(limit, 500)))).scalars().all()))
    return [ev_svc.event_dict(r) for r in rows]


@router.get("/api/v1/chat/tabs")
async def tabs(user: CurrentUser = Depends(require(P.CHAT_READ)), db: AsyncSession = Depends(get_db)):
    """Ein Reiter pro verbundenem Portal mit Anzahl Nachrichten der letzten 24h."""
    from apps.db.models import utcnow
    accounts = (await db.execute(select(PlatformAccount).where(PlatformAccount.tenant_id == user.tenant_id))).scalars().all()
    since = utcnow() - timedelta(hours=24)
    recent = (await db.execute(select(ChatEvent.platform).where(
        ChatEvent.tenant_id == user.tenant_id, ChatEvent.ts >= since, ChatEvent.is_outgoing.is_(False)))).scalars().all()
    return [{"platform": a.platform, "account": a.account_username, "enabled": a.enabled,
             "messages_24h": sum(1 for p in recent if p == a.platform)} for a in accounts]


@router.post("/api/v1/chat/reply", status_code=202)
async def reply(req: ReplyIn, background: BackgroundTasks, user: CurrentUser = Depends(require(P.CHAT_REPLY)),
                db: AsyncSession = Depends(get_db)):
    acc = (await db.execute(select(PlatformAccount).where(
        PlatformAccount.tenant_id == user.tenant_id, PlatformAccount.platform == req.platform.value,
        PlatformAccount.enabled.is_(True)))).scalars().first()
    if acc is None:
        raise HTTPException(409, "Kein aktives Konto fuer diese Plattform hinterlegt")
    e = Outbox(tenant_id=user.tenant_id, kind="chat_reply",
               payload={"platform": req.platform.value, "recipient": req.recipient, "text": req.text, "sent_by": user.sub})
    db.add(e)
    await db.commit()
    background.add_task(outbox.process, user.tenant_id)
    return {"status": "queued", "outbox_id": str(e.id)}


@router.post("/api/v1/ws/ticket")
async def ws_ticket(user: CurrentUser = Depends(require(P.CHAT_READ))):
    now = time.time()
    for k, (_, exp, _u) in list(_tickets.items()):
        if exp < now:
            _tickets.pop(k, None)
    t = secrets.token_urlsafe(24)
    _tickets[t] = (user.tenant_id, now + TICKET_TTL, user)
    return {"ticket": t, "expires_in": TICKET_TTL}


@router.websocket("/ws/v1/chat")
async def ws_chat(ws: WebSocket, ticket: str):
    entry = _tickets.pop(ticket, None)
    if entry is None or entry[1] < time.time():
        await ws.close(code=4401)
        return
    tenant_id, user = str(entry[0]), entry[2]
    await ws.accept()
    q = bus.subscribe(tenant_id)
    try:
        last_check = time.monotonic()
        while True:
            # removed members / "logout everywhere" must lose the live feed too – checked on a wall clock,
            # independent of how busy the chat is
            if user.account_version is not None and time.monotonic() - last_check >= 30:
                last_check = time.monotonic()
                try:
                    await _check_account(user)
                except HTTPException:
                    await ws.close(code=4401)
                    return
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})  # Heartbeat (Spec 5.3)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(tenant_id, q)
