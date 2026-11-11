"""Verarbeitung normalisierter Portal-Events: Persistenz, Automationen, Bus."""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.db.models import AutomationSettings, ChatEvent, GreetLog, Outbox, StreamSession, utcnow
from apps.domain.automation import goal_progress, render_template, should_greet
from apps.services.bus import bus


def event_dict(e: ChatEvent) -> dict:
    return {"id": e.id, "event_id": e.event_id, "platform": e.platform, "event_type": e.event_type,
            "ts": e.ts.isoformat(), "sender_id": e.sender_id, "sender_name": e.sender_name, "message": e.message,
            "tokens": e.tokens, "fiat_usd": e.fiat_usd, "is_outgoing": e.is_outgoing, "is_automated": e.is_automated}


async def ingest(db: AsyncSession, tenant_id: uuid.UUID, ev) -> tuple[ChatEvent | None, list[str]]:
    """Gibt (event, ausgeloeste_aktionen) zurueck; event=None bei Duplikat (idempotent)."""
    row = ChatEvent(tenant_id=tenant_id, event_id=ev.event_id, stream_id=ev.stream_id, platform=ev.platform.value,
                    event_type=ev.event_type.value, ts=ev.timestamp.replace(tzinfo=None),
                    sender_id=ev.sender.platform_user_id, sender_name=ev.sender.username,
                    message=ev.payload.message, tokens=ev.payload.tokens_spent, fiat_usd=ev.payload.fiat_equivalent_usd)
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return None, []

    actions: list[str] = []
    cfg = await db.get(AutomationSettings, tenant_id)
    now = utcnow()

    # Auto-Begruessung neuer Zuschauer
    if cfg and cfg.greet_enabled and ev.event_type.value == "join" and ev.sender.platform_user_id and \
            (not cfg.greet_platforms or ev.platform.value in cfg.greet_platforms):
        log = (await db.execute(select(GreetLog).where(
            GreetLog.tenant_id == tenant_id, GreetLog.platform == ev.platform.value,
            GreetLog.sender_id == ev.sender.platform_user_id))).scalar_one_or_none()
        if should_greet(log.last_greeted if log else None, now, cfg.greet_cooldown_hours):
            text = render_template(cfg.greet_template, username=ev.sender.username or "", platform=ev.platform.value)
            db.add(Outbox(tenant_id=tenant_id, kind="chat_reply", payload={
                "platform": ev.platform.value, "recipient": None, "text": text, "automated": True}))
            if log:
                log.last_greeted = now
            else:
                db.add(GreetLog(tenant_id=tenant_id, platform=ev.platform.value,
                                sender_id=ev.sender.platform_user_id, last_greeted=now))
            actions.append("greeting_queued")

    # Spendenziel der laufenden Session
    if ev.event_type.value == "tip" and ev.payload.tokens_spent > 0:
        sess = (await db.execute(select(StreamSession).where(
            StreamSession.tenant_id == tenant_id, StreamSession.ended_at.is_(None))
            .order_by(StreamSession.started_at.desc()).limit(1))).scalar_one_or_none()
        if sess:
            target = cfg.tip_goal_tokens if cfg else None
            prog = goal_progress(sess.tip_total, ev.payload.tokens_spent, target or 10**12)
            sess.tip_total = prog.total
            if target and prog.newly_reached and not sess.goal_reached:
                sess.goal_reached = True
                if cfg.obs_webhook_url:
                    db.add(Outbox(tenant_id=tenant_id, kind="obs_webhook", payload={
                        "url": cfg.obs_webhook_url, "event": "tip_goal_reached",
                        "label": cfg.tip_goal_label, "total": prog.total, "session_id": str(sess.id)}))
                actions.append("goal_reached")

    await db.commit()
    bus.publish(str(tenant_id), {"type": "chat_event", "event": event_dict(row), "actions": actions})
    return row, actions
