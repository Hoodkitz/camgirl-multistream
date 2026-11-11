"""Mandantenbezogener Zugriff auf das (lokale) KMS."""
from apps.core.config import settings
from apps.db.models import Tenant
from apps.domain.vault import KeyDestroyed, LocalKMS


def kms_for(tenant: Tenant) -> LocalKMS:
    store = {tenant.kek_ref: tenant.kek_blob} if tenant.kek_blob else {}
    return LocalKMS(settings.LOCAL_KMS_MASTER_KEY, store)


def new_tenant_kek(tenant: Tenant) -> None:
    kms = LocalKMS(settings.LOCAL_KMS_MASTER_KEY)
    tenant.kek_ref = kms.create_kek(str(tenant.id))
    tenant.kek_blob = kms.store[tenant.kek_ref]


def shred(tenant: Tenant) -> None:
    """Crypto-Shredding: KEK unwiderruflich vernichten."""
    tenant.kek_blob = None


__all__ = ["kms_for", "new_tenant_kek", "shred", "KeyDestroyed"]
