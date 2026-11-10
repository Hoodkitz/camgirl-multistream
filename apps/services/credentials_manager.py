from cryptography.fernet import Fernet
from apps.core.config import settings
import base64
import os

class CredentialsManager:
    def __init__(self):
        # We need a 32 url-safe base64-encoded byte string for Fernet
        key = settings.CREDENTIALS_KEY.encode() if hasattr(settings, 'CREDENTIALS_KEY') else Fernet.generate_key()
        try:
            self.cipher_suite = Fernet(key)
        except ValueError:
            # Fallback for invalid keys during tests/dev
            self.cipher_suite = Fernet(Fernet.generate_key())

    def encrypt(self, data: str) -> str:
        return self.cipher_suite.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher_suite.decrypt(encrypted_data.encode()).decode()
