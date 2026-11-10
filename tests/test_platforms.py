import pytest
from apps.api.schemas.platforms import PlatformAccountCreate
from apps.services.credentials_manager import CredentialsManager
from apps.core.models import Platform

def test_credentials_manager():
    manager = CredentialsManager()
    original = "my-super-secret-key"
    encrypted = manager.encrypt(original)
    assert encrypted != original
    decrypted = manager.decrypt(encrypted)
    assert decrypted == original
