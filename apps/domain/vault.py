"""KMS Envelope Encryption (Spec Kap. 6, ADR-04/08).

Pro Datensatz ein frischer 256-bit DEK, AES-256-GCM mit AAD = tenant_id:platform.
Der DEK wird mit dem mandantenspezifischen KEK eingewickelt. Loeschen des KEK
(Crypto-Shredding) macht alle Datensaetze des Mandanten – auch in Backups – unlesbar.

`LocalKMS` ist der Entwicklungs-Ersatz fuer ein Cloud-KMS/HSM: Tenant-KEKs werden selbst
mit dem Master-Key verschluesselt gespeichert. Austauschbar ueber das `KMS`-Protokoll.
"""
import base64
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class KeyDestroyed(Exception):
    pass


class DecryptionError(Exception):
    pass


class KMS(Protocol):
    def create_kek(self, tenant_id: str) -> str: ...
    def wrap(self, kek_ref: str, dek: bytes, context: bytes) -> bytes: ...
    def unwrap(self, kek_ref: str, wrapped: bytes, context: bytes) -> bytes: ...
    def destroy_kek(self, kek_ref: str) -> None: ...


class LocalKMS:
    """KEK-Speicher im Prozess bzw. ueber Callbacks persistiert (siehe services.kms)."""

    def __init__(self, master_key_b64: str, store: dict[str, bytes] | None = None):
        mk = base64.b64decode(master_key_b64)
        if len(mk) != 32:
            raise ValueError("Master-Key muss 32 Byte lang sein")
        self._master = AESGCM(mk)
        self.store: dict[str, bytes] = store if store is not None else {}

    def create_kek(self, tenant_id: str) -> str:
        ref = f"local-kek:{tenant_id}:{os.urandom(4).hex()}"
        nonce = os.urandom(12)
        self.store[ref] = nonce + self._master.encrypt(nonce, AESGCM.generate_key(256), ref.encode())
        return ref

    def _kek(self, ref: str) -> AESGCM:
        blob = self.store.get(ref)
        if blob is None:
            raise KeyDestroyed(ref)
        return AESGCM(self._master.decrypt(blob[:12], blob[12:], ref.encode()))

    def wrap(self, kek_ref: str, dek: bytes, context: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._kek(kek_ref).encrypt(nonce, dek, context)

    def unwrap(self, kek_ref: str, wrapped: bytes, context: bytes) -> bytes:
        try:
            return self._kek(kek_ref).decrypt(wrapped[:12], wrapped[12:], context)
        except InvalidTag as e:
            raise DecryptionError("DEK-Unwrap fehlgeschlagen") from e

    def destroy_kek(self, kek_ref: str) -> None:
        self.store.pop(kek_ref, None)


@dataclass
class Sealed:
    ciphertext: bytes
    wrapped_dek: bytes
    iv: bytes
    auth_tag: bytes


def context(tenant_id: str, platform: str) -> bytes:
    return f"{tenant_id}:{platform}".encode()


def seal(kms: KMS, kek_ref: str, tenant_id: str, platform: str, plaintext: bytes) -> Sealed:
    dek = bytearray(AESGCM.generate_key(256))
    try:
        iv = os.urandom(12)
        ct = AESGCM(bytes(dek)).encrypt(iv, plaintext, context(tenant_id, platform))
        wrapped = kms.wrap(kek_ref, bytes(dek), context(tenant_id, platform))
    finally:
        for i in range(len(dek)):  # zeroise (best effort in Python)
            dek[i] = 0
    return Sealed(ct[:-16], wrapped, iv, ct[-16:])


def unseal(kms: KMS, kek_ref: str, tenant_id: str, platform: str, s: Sealed) -> bytes:
    ctx = context(tenant_id, platform)
    dek = kms.unwrap(kek_ref, s.wrapped_dek, ctx)
    try:
        return AESGCM(dek).decrypt(s.iv, s.ciphertext + s.auth_tag, ctx)
    except InvalidTag as e:
        raise DecryptionError("Credential manipuliert oder falscher Mandant") from e
