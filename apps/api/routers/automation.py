from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas import AutomationIn, AutomationOut
from apps.core.permissions import Permission as P
from apps.db.models import AutomationSettings
from apps.domain.automation import render_template
from apps.security.auth import CurrentUser, get_db, require

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


async def _get(db, tenant_id) -> AutomationSettings:
    cfg = await db.get(AutomationSettings, tenant_id)
    if cfg is None:
        cfg = AutomationSettings(tenant_id=tenant_id)
        db.add(cfg)
        await db.flush()
    return cfg


@router.get("", response_model=AutomationOut)
async def get_automation(user: CurrentUser = Depends(require(P.AUTOMATION_MANAGE)), db: AsyncSession = Depends(get_db)):
    cfg = await _get(db, user.tenant_id)
    await db.commit()
    return cfg


@router.put("", response_model=AutomationOut)
async def put_automation(req: AutomationIn, user: CurrentUser = Depends(require(P.AUTOMATION_MANAGE)),
                         db: AsyncSession = Depends(get_db)):
    cfg = await _get(db, user.tenant_id)
    for k, v in req.model_dump(mode="json").items():
        setattr(cfg, k, v)
    await db.commit()
    return cfg


@router.post("/preview")
async def preview(template: str, username: str = "VipDonor99", user: CurrentUser = Depends(require(P.AUTOMATION_MANAGE))):
    return {"text": render_template(template, username=username, platform="stripchat")}
