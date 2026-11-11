import asyncio
import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp()
os.environ.update(ENV="test", DATABASE_URL=f"sqlite+aiosqlite:///{_tmp}/test.db",
                  JWT_SECRET="test-secret-0123456789abcdef0123456789", RATE_LIMIT_PER_MINUTE="1000",
                  KEY_STORE_DIR=f"{_tmp}/keys")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from apps.api.main import app  # noqa: E402
from apps.db.models import Base  # noqa: E402
from apps.db.session import engine  # noqa: E402
from apps.security.auth import issue_token  # noqa: E402
from apps.services import connectors  # noqa: E402


async def _reset():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def client():
    asyncio.run(_reset())
    connectors.connector = connectors.RecordingConnector()
    with TestClient(app) as c:
        yield c


def auth(tenant_id, *roles, sub="u1", **kw):
    return {"Authorization": f"Bearer {issue_token(sub, tenant_id, list(roles), **kw)}"}


@pytest.fixture
def tenant(client):
    tid = str(uuid.uuid4())
    H = lambda *r, **kw: auth(tid, *r, **kw)  # noqa: E731
    r = client.post("/api/v1/tenants", json={"name": "Luna Studio"}, headers=H("owner"))
    assert r.status_code == 201, r.text
    return tid, H


SRS = {"X-SRS-Secret": "dev-srs-secret"}
CONN = {"X-Connector-Secret": "dev-connector-secret"}
