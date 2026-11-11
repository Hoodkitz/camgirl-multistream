import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas import CredentialCreate, CredentialOut
from apps.core.permissions import Permission as P
from apps.db.models import PlatformAccount, Tenant
from apps.domain.vault import seal
from apps.security.auth import CurrentUser, get_db, require
from apps.services.kms import kms_for

router = APIRouter(prefix="/api/v1/credentials", tags=["credentials"])


async def tenant_or_404(db, user) -> Tenant:
    t = await db.get(Tenant, user.tenant_id)
    if t is None:
        raise HTTPException(404, "Mandant nicht angelegt")
    return t


@router.post("", response_model=CredentialOut, status_code=201)
async def add_credential(req: CredentialCreate, user: CurrentUser = Depends(require(P.CREDENTIALS_WRITE)),
                         db: AsyncSession = Depends(get_db)):
    t = await tenant_or_404(db, user)
    secret = json.dumps({"stream_key": req.stream_key, "api_token": req.api_token}).encode()
    s = seal(kms_for(t), t.kek_ref, str(t.id), req.platform.value, secret)
    acc = PlatformAccount(tenant_id=t.id, platform=req.platform.value, account_username=req.account_username,
                          ingest_url=req.ingest_url, encrypted_credentials=s.ciphertext, wrapped_dek=s.wrapped_dek,
                          iv=s.iv, auth_tag=s.auth_tag, kek_ref=t.kek_ref)
    db.add(acc)
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(409, "Konto fuer diese Plattform existiert bereits")
    return acc


@router.get("", response_model=list[CredentialOut])
async def list_credentials(user: CurrentUser = Depends(require(P.CREDENTIALS_READ)), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(PlatformAccount).where(PlatformAccount.tenant_id == user.tenant_id)
                             .order_by(PlatformAccount.platform))).scalars().all()


@router.patch("/{account_id}", response_model=CredentialOut)
async def toggle_credential(account_id: uuid.UUID, enabled: bool, user: CurrentUser = Depends(require(P.CREDENTIALS_WRITE)),
                            db: AsyncSession = Depends(get_db)):
    acc = await _owned(db, user, account_id)
    acc.enabled = enabled
    await db.commit()
    return acc


@router.delete("/{account_id}", status_code=204)
async def delete_credential(account_id: uuid.UUID, user: CurrentUser = Depends(require(P.CREDENTIALS_WRITE)),
                            db: AsyncSession = Depends(get_db)):
    """Sofortige physische Loeschung (Retention: Credentials)."""
    await db.delete(await _owned(db, user, account_id))
    await db.commit()


async def _owned(db, user, account_id) -> PlatformAccount:
    acc = (await db.execute(select(PlatformAccount).where(
        PlatformAccount.id == account_id, PlatformAccount.tenant_id == user.tenant_id))).scalar_one_or_none()
    if acc is None:
        raise HTTPException(404, "Konto nicht gefunden")
    return acc
