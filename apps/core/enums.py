from enum import Enum


class Role(str, Enum):
    OWNER = "owner"      # Model / Agenturinhaber
    CREATOR = "creator"  # Model innerhalb einer Agentur
    AGENT = "agent"      # Chat-Betreuer
    AUDIT = "audit"


class Platform(str, Enum):
    CHATURBATE = "chaturbate"
    STRIPCHAT = "stripchat"
    MYFREECAMS = "myfreecams"
    BONGACAMS = "bongacams"
    CAMSODA = "camsoda"
    CUSTOM = "custom"


class Tier(str, Enum):
    STANDARD = "standard"
    PRO = "pro"
    AGENCY = "agency"


class EventType(str, Enum):
    MESSAGE = "message"
    TIP = "tip"
    JOIN = "join"
    LEAVE = "leave"
    PRIVATE_REQUEST = "private_request"
    SYSTEM = "system"


# Standard-RTMP-Ingest der Portale (Stream-Key wird angehaengt). Konfigurierbar pro Konto.
DEFAULT_INGEST = {
    Platform.CHATURBATE: "rtmp://live.stream.highwebmedia.com/live-origin",
    Platform.STRIPCHAT: "rtmp://s-sd.stripst.com/ext",
    Platform.MYFREECAMS: "rtmp://publish.myfreecams.com/NxServer",
    Platform.BONGACAMS: "rtmp://origin.bcvcdn.com/live",
    Platform.CAMSODA: "rtmp://stream.camsoda.com/live",
}

# Quotas (Spec Kap. 10.2)
QUOTAS = {
    Tier.STANDARD: {"feeds": 1, "targets": 3},
    Tier.PRO: {"feeds": 1, "targets": 10},
    Tier.AGENCY: {"feeds": 3, "targets": 10},
}


def allowed_ingest_hosts() -> set[str]:
    from urllib.parse import urlsplit

    from apps.core.config import settings
    hosts = {urlsplit(u).hostname for u in DEFAULT_INGEST.values()}
    hosts |= {h.strip().lower() for h in settings.EXTRA_INGEST_HOSTS.split(",") if h.strip()}
    return hosts
