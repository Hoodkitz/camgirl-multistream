"""Token-Validierung, Benutzerkontext und RBAC-Dependencies.

Die Authentifizierung (OIDC Authorization Code + PKCE, Spec Kap. 8.1) findet beim
Identity Provider statt. Diese API validiert nur Bearer-Tokens und wertet die Claims
`sub`, `tenant_id` und `roles` aus. Ein Password-Grant existiert bewusst nicht.
"""
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from apps.core.config import settings
from apps.core.enums import Role
from apps.core.permissions import Permission, permissions_for
from apps.db.session import SessionLocal, set_tenant_context

bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    sub: str
    tenant_id: uuid.UUID
    roles: list[Role]
    permissions: set[Permission] = field(default_factory=set)
    auth_time: int | None = None

    def has(self, perm: Permission) -> bool:
        return perm in self.permissions


def issue_token(sub: str, tenant_id: str | uuid.UUID, roles: list[str], minutes: int | None = None,
                auth_time: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    claims = {"auth_time": auth_time or int(now.timestamp()),
        "sub": sub, "tenant_id": str(tenant_id), "roles": roles,
        "iss": settings.OIDC_ISSUER, "aud": settings.JWT_AUDIENCE,
        "iat": now, "exp": now + timedelta(minutes=minutes or settings.ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


REFRESH_DAYS = 30


def issue_refresh_token(sub: str, tenant_id, version: int, auth_time: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"typ": "refresh", "sub": sub, "tenant_id": str(tenant_id), "ver": version,
                       "auth_time": auth_time, "iss": settings.OIDC_ISSUER, "aud": settings.JWT_AUDIENCE + ":refresh",
                       "iat": now, "exp": now + timedelta(days=REFRESH_DAYS)},
                      settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_refresh_token(token: str) -> dict:
    try:
        c = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                       audience=settings.JWT_AUDIENCE + ":refresh", issuer=settings.OIDC_ISSUER,
                       options={"require": ["exp", "sub", "aud", "iss"]})
        if c.get("typ") != "refresh":
            raise ValueError("not a refresh token")
        return c
    except (jwt.PyJWTError, ValueError) as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung abgelaufen – bitte neu anmelden") from e


def decode_token(token: str) -> CurrentUser:
    try:
        c = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                       audience=settings.JWT_AUDIENCE, issuer=settings.OIDC_ISSUER,
                       options={"require": ["exp", "sub", "aud", "iss"]})
        tenant = uuid.UUID(c["tenant_id"])
        if c.get("typ") == "refresh":
            raise ValueError("refresh token used as access token")
    except (jwt.PyJWTError, KeyError, ValueError) as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungueltiges Token",
                            headers={"WWW-Authenticate": "Bearer"}) from e
    roles = []
    for r in c.get("roles", []):
        try:
            roles.append(Role(r))
        except ValueError:
            pass
    return CurrentUser(c["sub"], tenant, roles, permissions_for(roles), c.get("auth_time"))


async def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentUser:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht authentifiziert",
                            headers={"WWW-Authenticate": "Bearer"})
    return decode_token(cred.credentials)


def require(perm: Permission):
    async def dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has(perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Berechtigung fehlt: {perm.value}")
        return user
    return dep


async def get_db(user: CurrentUser = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped Session: setzt den RLS-Kontext transaktionslokal."""
    async with SessionLocal() as session:
        await set_tenant_context(session, str(user.tenant_id))
        yield session


def require_secret(header_value: str | None, expected: str) -> None:
    """Maschinen-Authentifizierung (SRS, Connectors) mit konstantzeitigem Vergleich."""
    import hmac
    if not header_value or not hmac.compare_digest(header_value, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungueltiges Service-Secret")
