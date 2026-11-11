"""Einnahmen, Zuschauer, Chat-Aktivitaet pro Portal."""
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core.permissions import Permission as P
from apps.db.models import ChatEvent, StreamSession, utcnow
from apps.security.auth import CurrentUser, get_db, require

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("/overview")
async def overview(days: int = Query(30, ge=1, le=365), user: CurrentUser = Depends(require(P.STATS_READ)),
                   db: AsyncSession = Depends(get_db)):
    since = utcnow() - timedelta(days=days)
    rows = (await db.execute(select(ChatEvent).where(
        ChatEvent.tenant_id == user.tenant_id, ChatEvent.ts >= since, ChatEvent.is_outgoing.is_(False)))).scalars().all()
    per = defaultdict(lambda: {"tokens": 0, "umsatz_usd": 0.0, "tips": 0, "nachrichten": 0, "joins": 0,
                               "chatter": set(), "top_spender": defaultdict(int)})
    for r in rows:
        p = per[r.platform]
        if r.event_type == "tip":
            p["tokens"] += r.tokens
            p["umsatz_usd"] += r.fiat_usd
            p["tips"] += 1
            if r.sender_name:
                p["top_spender"][r.sender_name] += r.tokens
        elif r.event_type == "message":
            p["nachrichten"] += 1
            if r.sender_id:
                p["chatter"].add(r.sender_id)
        elif r.event_type == "join":
            p["joins"] += 1
    sessions = (await db.execute(select(StreamSession).where(
        StreamSession.tenant_id == user.tenant_id, StreamSession.started_at >= since))).scalars().all()
    now = utcnow()
    hours = sum(((s.ended_at or now) - s.started_at).total_seconds() for s in sessions) / 3600
    plattformen = {}
    for name, p in per.items():
        top = sorted(p["top_spender"].items(), key=lambda kv: -kv[1])[:5]
        plattformen[name] = {"tokens": p["tokens"], "umsatz_usd": round(p["umsatz_usd"], 2), "tips": p["tips"],
                             "nachrichten": p["nachrichten"], "joins": p["joins"], "aktive_chatter": len(p["chatter"]),
                             "top_spender": [{"name": n, "tokens": t} for n, t in top]}
    total = sum(p["umsatz_usd"] for p in plattformen.values())
    return {"zeitraum_tage": days, "umsatz_usd_gesamt": round(total, 2), "streams": len(sessions),
            "stream_stunden": round(hours, 2),
            "umsatz_pro_stunde_usd": round(total / hours, 2) if hours else None, "plattformen": plattformen}
