"""Built-in accounts: sign-up (creates the tenant), login, re-authentication, team members.

Lookups by e-mail span tenants, so this router uses the system session (BYPASSRLS); everything it returns is
scoped to the caller. Passwords: Argon2id. Brute force: per-account lockout plus the global rate limit.
"""
import time
import uuid
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update

from apps.core.enums import Role
from apps.core.permissions import Permission as P
from apps.db import models as m
from apps.db.session import SystemSessionLocal
from apps.core.config import settings
from apps.security.auth import (CurrentUser, decode_refresh_token, get_current_user, issue_refresh_token, issue_token,
                                require)
from apps.services.kms import new_tenant_kek

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_ph = PasswordHasher()
_DUMMY = _ph.hash("timing-equaliser-not-a-password")
MAX_FAILED = 5
LOCK_MINUTES = 15


class SignUp(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    tenant_name: str = Field(min_length=1, max_length=255)


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class Reauth(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class TeamMember(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    role: Role = Role.AGENT


class Refresh(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=4096)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: uuid.UUID
    role: str


def _token(u: m.User, auth_time: int | None = None) -> TokenOut:
    at = auth_time or int(time.time())
    return TokenOut(access_token=issue_token(str(u.id), u.tenant_id, [u.role], auth_time=at, ver=u.token_version or 0),
                    refresh_token=issue_refresh_token(str(u.id), u.tenant_id, u.token_version or 0, at),
                    expires_in=settings.ACCESS_TOKEN_MINUTES * 60, tenant_id=u.tenant_id, role=u.role)


async def _by_email(db, email: str) -> m.User | None:
    return (await db.execute(select(m.User).where(func.lower(m.User.email) == email.lower()))).scalars().first()


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(req: SignUp):
    async with SystemSessionLocal() as db:
        if await _by_email(db, req.email):
            raise HTTPException(409, "E-Mail ist bereits registriert")
        t = m.Tenant(id=uuid.uuid4(), name=req.tenant_name, kek_ref="")
        new_tenant_kek(t)
        db.add(t)
        await db.flush()
        db.add(m.AutomationSettings(tenant_id=t.id))
        u = m.User(tenant_id=t.id, email=req.email.lower(), password_hash=_ph.hash(req.password),
                   role=Role.OWNER.value, last_login_at=m.utcnow())
        db.add(u)
        await db.commit()
        return _token(u)


async def _check_password(db, u: m.User | None, password: str) -> bool:
    if u is None:
        try:
            _ph.verify(_DUMMY, password)  # same work as a real check: no user enumeration by timing
        except VerificationError:
            pass
        return False
    if u.locked_until and u.locked_until > m.utcnow():
        raise HTTPException(429, "Zu viele Fehlversuche – Konto vorübergehend gesperrt")
    try:
        _ph.verify(u.password_hash, password)
    except (VerificationError, InvalidHashError):
        # atomic increment: parallel guesses cannot all read the same counter value
        n = (await db.execute(update(m.User).where(m.User.id == u.id)
                              .values(failed_logins=m.User.failed_logins + 1)
                              .returning(m.User.failed_logins))).scalar_one()
        if n >= MAX_FAILED:
            await db.execute(update(m.User).where(m.User.id == u.id)
                             .values(locked_until=m.utcnow() + timedelta(minutes=LOCK_MINUTES), failed_logins=0))
        await db.commit()
        return False
    if _ph.check_needs_rehash(u.password_hash):
        u.password_hash = _ph.hash(password)
    u.failed_logins = 0
    u.locked_until = None
    u.last_login_at = m.utcnow()
    await db.commit()
    return True


@router.post("/login", response_model=TokenOut)
async def login(req: Login):
    async with SystemSessionLocal() as db:
        u = await _by_email(db, req.email)
        if not await _check_password(db, u, req.password):
            raise HTTPException(401, "E-Mail oder Passwort falsch")
        return _token(u)


@router.post("/refresh", response_model=TokenOut)
async def refresh(req: Refresh):
    """New access token; keeps the original login time (re-auth stays required for sensitive actions)."""
    c = decode_refresh_token(req.refresh_token)
    async with SystemSessionLocal() as db:
        try:
            u = await db.get(m.User, uuid.UUID(c["sub"]))
        except ValueError:
            u = None
        if u is None or str(u.tenant_id) != c.get("tenant_id") or (u.token_version or 0) != c.get("ver"):
            raise HTTPException(401, "Sitzung abgelaufen – bitte neu anmelden")
        return _token(u, auth_time=int(c.get("auth_time") or 0) or None)


@router.post("/logout-all", status_code=204)
async def logout_everywhere(user: CurrentUser = Depends(get_current_user)):
    """Revokes every refresh token of this account (e.g. lost phone)."""
    async with SystemSessionLocal() as db:
        u = await db.get(m.User, _uid(user))
        if u is not None and u.tenant_id == user.tenant_id:
            u.token_version = (u.token_version or 0) + 1
            await db.commit()


@router.post("/reauth", response_model=TokenOut)
async def reauth(req: Reauth, user: CurrentUser = Depends(get_current_user)):
    """Fresh auth_time for sensitive actions (account deletion requires a login younger than 5 minutes)."""
    async with SystemSessionLocal() as db:
        u = await db.get(m.User, _uid(user))
        if u is None or u.tenant_id != user.tenant_id:
            raise HTTPException(401, "Konto nicht gefunden")
        if not await _check_password(db, u, req.password):
            raise HTTPException(401, "Passwort falsch")
        return _token(u)


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    async with SystemSessionLocal() as db:
        u = await db.get(m.User, _uid(user))
        if u is None or u.tenant_id != user.tenant_id:
            raise HTTPException(404, "Kein eingebautes Konto (externer Identity Provider)")
        return {"id": str(u.id), "email": u.email, "role": u.role, "tenant_id": str(u.tenant_id)}


@router.get("/team")
async def list_team(user: CurrentUser = Depends(require(P.TENANT_DELETE))):
    async with SystemSessionLocal() as db:
        rows = (await db.execute(select(m.User).where(m.User.tenant_id == user.tenant_id)
                                 .order_by(m.User.created_at))).scalars().all()
        return [{"id": str(u.id), "email": u.email, "role": u.role} for u in rows]


@router.post("/team", status_code=201)
async def add_team_member(req: TeamMember, user: CurrentUser = Depends(require(P.TENANT_DELETE))):
    """Owner adds a creator/agent/audit account with an initial password (to be handed over securely)."""
    if req.role == Role.OWNER:
        raise HTTPException(422, "Es gibt genau einen Inhaber pro Konto")
    async with SystemSessionLocal() as db:
        if await _by_email(db, req.email):
            raise HTTPException(409, "E-Mail ist bereits registriert")
        u = m.User(tenant_id=user.tenant_id, email=req.email.lower(), password_hash=_ph.hash(req.password),
                   role=req.role.value)
        db.add(u)
        await db.commit()
        return {"id": str(u.id), "email": u.email, "role": u.role}


@router.delete("/team/{member_id}", status_code=204)
async def remove_team_member(member_id: uuid.UUID, user: CurrentUser = Depends(require(P.TENANT_DELETE))):
    async with SystemSessionLocal() as db:
        u = await db.get(m.User, member_id)
        if u is None or u.tenant_id != user.tenant_id:
            raise HTTPException(404, "Mitglied nicht gefunden")
        if u.role == Role.OWNER.value:
            raise HTTPException(422, "Der Inhaber kann nicht entfernt werden")
        await db.delete(u)
        await db.commit()


def _uid(user: CurrentUser) -> uuid.UUID:
    try:
        return uuid.UUID(user.sub)
    except ValueError:
        raise HTTPException(404, "Kein eingebautes Konto (externer Identity Provider)")
