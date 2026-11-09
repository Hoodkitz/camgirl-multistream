"""Tests for domain models."""
from packages.domain.models import PlatformAccount, StreamSession, Platform, ChatEvent
from uuid import uuid4
from datetime import datetime


def test_platform_account():
    pa = PlatformAccount(tenant_id=uuid4(), platform_name=Platform.CHATURBATE, account_username="test", encrypted_credentials=b"enc", wrapped_dek=b"dek", iv=b"iv")
    assert pa.platform_name == Platform.CHATURBATE


def test_stream_session():
    ss = StreamSession(tenant_id=uuid4(), ingest_protocol="rtmp", target_platforms=[Platform.CHATURBATE, Platform.STRIPCHAT])
    assert ss.is_active is True
    assert len(ss.target_platforms) == 2
