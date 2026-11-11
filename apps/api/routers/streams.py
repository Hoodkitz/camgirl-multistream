"""Ingest-Autorisierung und dynamisches Fan-Out fuer SRS (Spec Kap. 4)."""
import hashlib
import json
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas import SessionOut, SrsHook, StreamKeyCreate, StreamKeyCreated, StreamKeyOut, TargetOut
from apps.core.config import settings
from apps.core.enums import DEFAULT_INGEST, QUOTAS, Platform, Tier
from apps.core.permissions import Permission as P
from apps.db.models import PlatformAccount, StreamKey, StreamSession, Tenant, utcnow
from apps.db.session import SystemSessionLocal as SessionLocal
from apps.domain.vault import Sealed, unseal
from apps.security.auth import CurrentUser, get_db, require, require_secret
from apps.services.kms import kms_for

router = APIRouter(prefix="/api/v1/streams", tags=["streams"])
INGEST_HOST = "ingest.example.invalid"


def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


# --------------------------------------------------------------------------- Creator-API

@router.post("/keys", response_model=StreamKeyCreated, status_code=201)
async def create_stream_key(req: StreamKeyCreate, user: CurrentUser = Depends(require(P.STREAM_MANAGE)),
                            db: AsyncSession = Depends(get_db)):
    if await db.get(Tenant, user.tenant_id) is None:
        raise HTTPException(404, "Mandant nicht angelegt")
    raw = "sk_" + secrets.token_urlsafe(24)
    k = StreamKey(tenant_id=user.tenant_id, key_hash=hash_key(raw), label=req.label)
    db.add(k)
    await db.commit()
    return StreamKeyCreated(id=k.id, label=k.label, revoked=False, created_at=k.created_at, stream_key=raw,
                            rtmp_url=f"rtmp://{INGEST_HOST}:1935/live/{raw}",
                            srt_url=f"srt://{INGEST_HOST}:6000?streamid=#!::r=live/{raw},m=publish")


@router.get("/keys", response_model=list[StreamKeyOut])
async def list_stream_keys(user: CurrentUser = Depends(require(P.STREAM_MANAGE)), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(StreamKey).where(StreamKey.tenant_id == user.tenant_id))).scalars().all()


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_stream_key(key_id: uuid.UUID, user: CurrentUser = Depends(require(P.STREAM_MANAGE)),
                            db: AsyncSession = Depends(get_db)):
    k = (await db.execute(select(StreamKey).where(StreamKey.id == key_id, StreamKey.tenant_id == user.tenant_id))
         ).scalar_one_or_none()
    if k is None:
        raise HTTPException(404, "Stream-Key nicht gefunden")
    k.revoked = True
    await db.commit()


async def build_targets(db: AsyncSession, tenant: Tenant) -> list[TargetOut]:
    quota = QUOTAS[Tier(tenant.tier)]["targets"]
    accounts = (await db.execute(select(PlatformAccount).where(
        PlatformAccount.tenant_id == tenant.id, PlatformAccount.enabled.is_(True))
        .order_by(PlatformAccount.created_at))).scalars().all()[:quota]
    kms = kms_for(tenant)
    out = []
    for a in accounts:
        creds = json.loads(unseal(kms, a.kek_ref, str(tenant.id), a.platform,
                                  Sealed(a.encrypted_credentials, a.wrapped_dek, a.iv, a.auth_tag)))
        base = a.ingest_url or DEFAULT_INGEST.get(Platform(a.platform))
        if base:
            out.append(TargetOut(platform=a.platform, account_username=a.account_username,
                                 url=f"{base.rstrip('/')}/{creds['stream_key']}"))
    return out


@router.get("/targets", response_model=list[TargetOut])
async def get_targets(user: CurrentUser = Depends(require(P.STREAM_MANAGE)), db: AsyncSession = Depends(get_db)):
    """Aktive Restream-Ziele; Portal-Keys maskiert."""
    t = await db.get(Tenant, user.tenant_id)
    if t is None:
        raise HTTPException(404, "Mandant nicht angelegt")
    targets = await build_targets(db, t)
    for x in targets:
        base, _, key = x.url.rpartition("/")
        x.url = f"{base}/{key[:3]}…{key[-2:]}" if len(key) > 6 else f"{base}/***"
    return targets


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(limit: int = 50, user: CurrentUser = Depends(require(P.STATS_READ)), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(StreamSession).where(StreamSession.tenant_id == user.tenant_id)
                             .order_by(StreamSession.started_at.desc()).limit(min(limit, 500)))).scalars().all()


# --------------------------------------------------------------------------- SRS-Callbacks

def _check_srs(request: Request, secret: str | None) -> None:
    require_secret(secret, settings.SRS_CALLBACK_SECRET)
    allowed = {ip.strip() for ip in settings.SRS_ALLOWED_IPS.split(",") if ip.strip()}
    if allowed and request.client and request.client.host not in allowed:
        raise HTTPException(403, "IP nicht freigegeben")


@router.post("/verify")
async def srs_hook(hook: SrsHook, request: Request, secret: str | None = Header(None, alias="X-SRS-Secret")):
    """on_publish: Key + Quota pruefen. on_forward: Ziel-URLs liefern. on_unpublish: Session schliessen.
    Antwortformat SRS: {"code": 0} = erlaubt, alles andere = abgelehnt."""
    _check_srs(request, secret)
    async with SessionLocal() as db:
        key = (await db.execute(select(StreamKey).where(StreamKey.key_hash == hash_key(hook.stream),
                                                        StreamKey.revoked.is_(False)))).scalar_one_or_none()
        if key is None:
            raise HTTPException(403, "Unbekannter oder widerrufener Stream-Key")
        tenant = await db.get(Tenant, key.tenant_id)

        if hook.action == "on_publish":
            active = (await db.execute(select(func.count()).select_from(StreamSession).where(
                StreamSession.tenant_id == tenant.id, StreamSession.ended_at.is_(None)))).scalar_one()
            if active >= QUOTAS[Tier(tenant.tier)]["feeds"]:
                raise HTTPException(429, "Maximale Anzahl paralleler Ingest-Feeds erreicht")
            targets = await build_targets(db, tenant)
            db.add(StreamSession(tenant_id=tenant.id, stream_key_id=key.id, srs_client_id=hook.client_id,
                                 protocol="srt" if (hook.param or "").find("srt") >= 0 else "rtmp",
                                 targets=[t.platform for t in targets]))
            await db.commit()
            return {"code": 0}

        if hook.action == "on_forward":
            return {"code": 0, "data": {"urls": [t.url for t in await build_targets(db, tenant)]}}

        if hook.action == "on_unpublish":
            sess = (await db.execute(select(StreamSession).where(
                StreamSession.tenant_id == tenant.id, StreamSession.srs_client_id == hook.client_id,
                StreamSession.ended_at.is_(None)))).scalar_one_or_none()
            if sess:
                sess.ended_at, sess.end_reason = utcnow(), "unpublish"
                await db.commit()
            return {"code": 0}
    raise HTTPException(400, f"Unbekannte Aktion {hook.action}")


@router.post("/overdue")
async def overdue_sessions(request: Request, secret: str | None = Header(None, alias="X-SRS-Secret")):
    """Wall-Time-Cap (24h): beendet ueberlange Sessions; Rueckgabe = SRS-Client-IDs zum Kicken."""
    _check_srs(request, secret)
    limit = utcnow() - timedelta(hours=settings.STREAM_WALL_TIME_HOURS)
    async with SessionLocal() as db:
        rows = (await db.execute(select(StreamSession).where(
            StreamSession.ended_at.is_(None), StreamSession.started_at < limit))).scalars().all()
        for s in rows:
            s.ended_at, s.end_reason = utcnow(), "wall_time_cap"
        await db.commit()
        return {"kick_client_ids": [s.srs_client_id for s in rows]}
