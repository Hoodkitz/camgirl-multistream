from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import uuid
from apps.api.schemas.platforms import PlatformAccountCreate, PlatformAccountResponse
from apps.db.session import get_session
from apps.db.models import PlatformAccount as PlatformAccountModel, Tenant as TenantModel
from apps.api.security import require_role
from apps.services.credentials_manager import CredentialsManager

router = APIRouter(prefix="/platforms", tags=["platforms"])
cred_manager = CredentialsManager()

@router.post("", response_model=PlatformAccountResponse)
async def create_platform_account(req: PlatformAccountCreate, session: AsyncSession = Depends(get_session), current_user: dict = Depends(require_role("model"))):
    if current_user.get("tenant_id") and str(req.tenant_id) != current_user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    # Encrypt stream key
    encrypted_key = cred_manager.encrypt(req.stream_key)

    db_account = PlatformAccountModel(
        id=uuid.uuid4(),
        tenant_id=req.tenant_id,
        platform_name=req.platform_name,
        account_username=req.account_username,
        encrypted_credentials=encrypted_key,
        # Default empty values for unused fields for now
        wrapped_dek="N/A",
        iv="N/A",
        auth_tag="N/A"
    )
    session.add(db_account)
    await session.commit()
    return db_account

@router.get("/tenant/{tenant_id}", response_model=list[PlatformAccountResponse])
async def get_tenant_platforms(tenant_id: UUID, session: AsyncSession = Depends(get_session), current_user: dict = Depends(require_role("model"))):
    if current_user.get("tenant_id") and str(tenant_id) != current_user.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    stmt = select(PlatformAccountModel).where(PlatformAccountModel.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return [p async for p in result.scalars]
