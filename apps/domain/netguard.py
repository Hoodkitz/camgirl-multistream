"""SSRF-Schutz fuer serverseitige Ziel-URLs (OBS-Webhooks, Portal-Ingest)."""
import ipaddress
import socket


def _is_public_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast
                or a.is_unspecified)


def assert_public_host(host: str, port: int = 443) -> list[str]:
    """Loest den Host auf und lehnt private/lokale Ziele ab. Gibt die erlaubten IPs zurueck."""
    if not host:
        raise ValueError("Host fehlt")
    try:
        ipaddress.ip_address(host)
        candidates = [host]
    except ValueError:
        try:
            candidates = sorted({ai[4][0] for ai in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})
        except socket.gaierror as e:
            raise ValueError(f"Host nicht aufloesbar: {host}") from e
    if not candidates or not all(_is_public_ip(ip) for ip in candidates):
        raise ValueError("Ziel zeigt auf ein internes oder reserviertes Netz")
    return candidates


def is_ip_literal_private(host: str) -> bool:
    host = host.strip("[]")
    try:
        return not _is_public_ip(host)
    except ValueError:
        return host.lower() in ("localhost",) or host.lower().endswith((".local", ".internal", ".localhost"))
