"""Tests for envelope encryption."""
from packages.security.encryption import EnvelopeEncryption


def test_encrypt_decrypt():
    enc = EnvelopeEncryption()
    plaintext = b"secret credentials"
    ct, dek, iv, tag = enc.encrypt(plaintext)
    decrypted = enc.decrypt(ct, dek, iv, tag)
    assert decrypted == plaintext
