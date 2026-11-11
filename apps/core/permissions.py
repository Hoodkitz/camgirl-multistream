from enum import Enum

from apps.core.enums import Role


class Permission(str, Enum):
    CREDENTIALS_WRITE = "credentials:write"
    CREDENTIALS_READ = "credentials:read"   # nur Metadaten, nie Klartext
    STREAM_MANAGE = "stream:manage"
    CHAT_READ = "chat:read"
    CHAT_REPLY = "chat:reply"
    AUTOMATION_MANAGE = "automation:manage"
    STATS_READ = "stats:read"
    TENANT_DELETE = "tenant:delete"
    AUDIT_READ = "audit:read"


P = Permission
PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(P),
    Role.CREATOR: frozenset({P.CREDENTIALS_WRITE, P.CREDENTIALS_READ, P.STREAM_MANAGE, P.CHAT_READ, P.CHAT_REPLY,
                             P.AUTOMATION_MANAGE, P.STATS_READ}),
    Role.AGENT: frozenset({P.CHAT_READ, P.CHAT_REPLY, P.STATS_READ}),
    Role.AUDIT: frozenset({P.STATS_READ, P.AUDIT_READ}),
}


def permissions_for(roles) -> set[Permission]:
    out: set[Permission] = set()
    for r in roles:
        try:
            out |= PERMISSIONS[Role(r)]
        except ValueError:
            pass
    return out
