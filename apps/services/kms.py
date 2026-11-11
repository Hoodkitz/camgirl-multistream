"""Mandantenbezogener Zugriff auf das KMS.

Die Tenant-KEKs liegen bewusst NICHT in der Anwendungsdatenbank: Ein DB-Backup enthaelt
damit nur Ciphertexte und eingewickelte DEKs. Das Loeschen der Schluesseldatei (bzw. in
Produktion die Schluesselvernichtung im Cloud-KMS/HSM) macht alle Backups des Mandanten
unlesbar (Crypto-Shredding). Das Schluesselverzeichnis darf nicht mit der DB gesichert werden.
"""
import os
import re
from pathlib import Path

from apps.core.config import settings
from apps.db.models import Tenant
from apps.domain.vault import KeyDestroyed, LocalKMS


def _path(kek_ref: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", kek_ref)
    return Path(settings.KEY_STORE_DIR) / f"{safe}.kek"


def kms_for(tenant: Tenant) -> LocalKMS:
    p = _path(tenant.kek_ref)
    store = {tenant.kek_ref: p.read_bytes()} if p.exists() else {}
    return LocalKMS(settings.LOCAL_KMS_MASTER_KEY, store)


def new_tenant_kek(tenant: Tenant) -> None:
    kms = LocalKMS(settings.LOCAL_KMS_MASTER_KEY)
    tenant.kek_ref = kms.create_kek(str(tenant.id))
    p = _path(tenant.kek_ref)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(kms.store[tenant.kek_ref])


def shred(tenant: Tenant) -> bool:
    """Vernichtet den KEK. True nur, wenn danach wirklich kein Schluessel mehr existiert."""
    p = _path(tenant.kek_ref)
    if p.exists():
        size = p.stat().st_size
        with open(p, "r+b") as f:  # best effort ueberschreiben; echte Vernichtung leistet erst ein HSM
            f.write(os.urandom(size))
            f.flush()
            os.fsync(f.fileno())
        p.unlink()
    return not p.exists()


__all__ = ["kms_for", "new_tenant_kek", "shred", "KeyDestroyed"]
