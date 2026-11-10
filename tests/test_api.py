import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from apps.db.models import Tenant
import uuid
from apps.api.security import create_access_token
from datetime import timedelta

@pytest.mark.asyncio
async def test_healthcheck():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_create_stream(override_get_session, db_session):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Test Tenant")
    db_session.add(tenant)
    await db_session.commit()

    token = create_access_token({"sub": "testuser", "role": "model", "tenant_id": str(tenant_id)}, timedelta(minutes=15))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/streams", json={
            "tenant_id": str(tenant_id),
            "ingest_protocol": "rtmp",
            "target_platforms": ["chaturbate", "stripchat"]
        }, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(tenant_id)

@pytest.mark.asyncio
async def test_tenant_isolation(override_get_session, db_session):
    tenant1_id = uuid.uuid4()
    tenant2_id = uuid.uuid4()
    tenant1 = Tenant(id=tenant1_id, name="Test Tenant 1")
    tenant2 = Tenant(id=tenant2_id, name="Test Tenant 2")
    db_session.add_all([tenant1, tenant2])
    await db_session.commit()

    token1 = create_access_token({"sub": "user1", "role": "model", "tenant_id": str(tenant1_id)}, timedelta(minutes=15))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/stats/tenant/{str(tenant2_id)}/overview", headers={"Authorization": f"Bearer {token1}"})
        assert response.status_code == 403
