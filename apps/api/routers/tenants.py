import time

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas import TenantCreate, TenantOut
from apps.core.permissions import Permission as P
from apps.db import models as m
from apps.security.auth import CurrentUser, get_current_user, get_db, require
from apps.services.kms import new_tenant_kek, shred

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])
REAUTH_SECONDS = 300


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(req: TenantCreate, user: CurrentUser = Depends(require(P.TENANT_DELETE)),
                        db: AsyncSession = Depends(get_db)):
    """Onboarding: legt den Mandanten aus dem Token an (nur Owner)."""
    if await db.get(m.Tenant, user.tenant_id):
        raise HTTPException(409, "Mandant existiert bereits")
    t = m.Tenant(id=user.tenant_id, name=req.name, kek_ref="")
    new_tenant_kek(t)
    db.add(t)
    db.add(m.AutomationSettings(tenant_id=t.id))
    await db.commit()
    return t


@router.get("/me", response_model=TenantOut)
async def me(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = await db.get(m.Tenant, user.tenant_id)
    if t is None:
        raise HTTPException(404, "Mandant nicht angelegt")
    return t


@router.delete("/me")
async def delete_me(confirm: str = Header(..., alias="X-Confirm-Delete"),
                    user: CurrentUser = Depends(require(P.TENANT_DELETE)), db: AsyncSession = Depends(get_db)):
    """DSGVO Art. 17: physische Loeschkaskade + Crypto-Shredding des Mandanten-KEK."""
    t = await db.get(m.Tenant, user.tenant_id)
    if t is None:
        raise HTTPException(404, "Mandant nicht gefunden")
    if not user.auth_time or time.time() - user.auth_time > REAUTH_SECONDS:
        raise HTTPException(401, "Erneute Anmeldung erforderlich (max. 5 Minuten alt)")
    if confirm != t.name:
        raise HTTPException(422, "Bestaetigung stimmt nicht mit dem Mandantennamen ueberein")
    shredded = shred(t)  # zuerst: macht Backups sofort unlesbar
    if not shredded:
        raise HTTPException(500, "Schluesselvernichtung fehlgeschlagen, Loeschung abgebrochen")
    for model in (m.ChatEvent, m.GreetLog, m.Outbox, m.StreamSession, m.StreamKey, m.PlatformAccount,
                  m.AutomationSettings):
        await db.execute(delete(model).where(model.tenant_id == t.id))
    await db.delete(t)
    await db.commit()
    return {"status": "geloescht", "crypto_shredded": shredded}
