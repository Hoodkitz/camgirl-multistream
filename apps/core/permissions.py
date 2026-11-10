"""Permissions for CamGirl Multi-Stream."""
from enum import Enum
from typing import Set


class Permission(str, Enum):
    READ_PLATFORM = "read:platform"
    CREATE_PLATFORM = "create:platform"
    UPDATE_PLATFORM = "update:platform"
    READ_CHAT = "read:chat"
    SEND_REPLY = "send:reply"
    READ_STATS = "read:stats"
    TRIGGER_STREAM = "trigger:stream"
    EXPORT = "export"


class Role(str, Enum):
    MODEL = "model"
    ADMIN = "admin"
    AGENT = "agent"
    AUDIT = "audit"


PERMISSIONS: dict[Role, set[str]] = {
    Role.MODEL: {
        Permission.READ_PLATFORM, Permission.CREATE_PLATFORM, Permission.UPDATE_PLATFORM,
        Permission.READ_CHAT, Permission.SEND_REPLY, Permission.READ_STATS, Permission.EXPORT,
    },
    Role.ADMIN: {
        Permission.READ_PLATFORM, Permission.CREATE_PLATFORM, Permission.UPDATE_PLATFORM,
        Permission.READ_CHAT, Permission.SEND_REPLY, Permission.READ_STATS,
        Permission.TRIGGER_STREAM, Permission.EXPORT,
    },
    Role.AGENT: {
        Permission.READ_CHAT, Permission.SEND_REPLY, Permission.READ_STATS, Permission.TRIGGER_STREAM,
    },
    Role.AUDIT: {
        Permission.READ_CHAT, Permission.READ_STATS, Permission.EXPORT,
    },
}
