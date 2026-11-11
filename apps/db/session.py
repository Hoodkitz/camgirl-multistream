from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
system_engine = create_async_engine(settings.SYSTEM_DATABASE_URL, future=True) if settings.SYSTEM_DATABASE_URL else engine
SystemSessionLocal = async_sessionmaker(system_engine, class_=AsyncSession, expire_on_commit=False)


async def init_models() -> None:
    from apps.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def set_tenant_context(session: AsyncSession, tenant_id: str) -> None:
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
