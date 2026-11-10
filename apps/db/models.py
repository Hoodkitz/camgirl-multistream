"""SQLAlchemy models."""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, JSON, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    kms_kek_arn = Column(String(500), default="arn:aws:kms:us-east-1:123456789012:key/example")
    created_at = Column(DateTime, server_default="NOW()")
    is_active = Column(Boolean, default=True)


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    platform_name = Column(String(50), nullable=False)
    account_username = Column(String(255), nullable=False)
    encrypted_credentials = Column(Text, nullable=False)
    wrapped_dek = Column(Text, nullable=False)
    iv = Column(Text, nullable=False)
    auth_tag = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default="NOW()")
    is_active = Column(Boolean, default=True)
    tenant = relationship("Tenant", back_populates="platform_accounts")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    event_id = Column(String(255), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    stream_id = Column(String(255), nullable=False)
    platform = Column(String(50), nullable=False)
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    sender = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=False)
    tenant = relationship("Tenant")
    __table_args__ = ({"extend_existing": True})


class StreamSession(Base):
    __tablename__ = "stream_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    ingest_protocol = Column(String(50), default="rtmp")
    target_platforms = Column(JSON, default=list)
    started_at = Column(DateTime, server_default="NOW()")
    ended_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    viewer_count = Column(Integer, default=0)
    stats = Column(JSON, default=dict)
    tenant = relationship("Tenant", back_populates="stream_sessions")


class Tenant.stream_sessions = relationship("StreamSession", back_populates="tenant")
