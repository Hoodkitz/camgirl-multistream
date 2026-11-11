"""Postgres row-level security as the real application role (runs only when PG_APP_URL is set).

PG_APP_URL=postgresql://application_role:<pw>@localhost:5432/<db>  after `alembic upgrade head` as owner.
"""
import asyncio
import os
import uuid
from datetime import datetime

import pytest

asyncpg = pytest.importorskip("asyncpg")
URL = os.environ.get("PG_APP_URL")
pytestmark = pytest.mark.skipif(not URL, reason="PG_APP_URL not set")


async def _as(conn, tenant):
    await conn.execute("SELECT set_config('app.tenant_id', $1, false)", str(tenant) if tenant else "")


async def _scenario():
    conn = await asyncpg.connect(URL)
    try:
        a, b = uuid.uuid4(), uuid.uuid4()
        now = datetime.utcnow()
        for t in (a, b):
            await conn.execute("INSERT INTO tenants (id, name, tier, kek_ref, created_at) VALUES ($1, 'T', 'standard', 'k', $2)", t, now)
        await _as(conn, a)
        await conn.execute("INSERT INTO stream_keys (id, tenant_id, key_hash, label, revoked, created_at) VALUES ($1, $2, md5(random()::text), 'x', false, $3)", uuid.uuid4(), a, now)
        rows_a = await conn.fetchval("SELECT count(*) FROM stream_keys WHERE tenant_id = $1", a)
        await _as(conn, b)
        rows_seen_by_b = await conn.fetchval("SELECT count(*) FROM stream_keys WHERE tenant_id = $1", a)
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await conn.execute("INSERT INTO stream_keys (id, tenant_id, key_hash, label, revoked, created_at) VALUES ($1, $2, md5(random()::text), 'x', false, $3)", uuid.uuid4(), a, now)  # writing into another tenant
        await _as(conn, None)
        rows_without_context = await conn.fetchval("SELECT count(*) FROM stream_keys")
        return rows_a, rows_seen_by_b, rows_without_context
    finally:
        await conn.close()


def test_rls_isolates_tenants():
    rows_a, rows_seen_by_b, rows_without_context = asyncio.run(_scenario())
    assert rows_a == 1
    assert rows_seen_by_b == 0
    assert rows_without_context == 0
