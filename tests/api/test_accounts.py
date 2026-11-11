"""Built-in accounts: sign-up creates the tenant, login/refresh/lockout, re-auth for deletion, team, isolation."""
import time

from apps.security import auth as sec


def signup(client, email="model@example.com", name="Studio Luna"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-1", "tenant_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def H(tok):
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_signup_login_and_use_api(client):
    tok = signup(client)
    assert tok["role"] == "owner"
    me = client.get("/api/v1/tenants/me", headers=H(tok)).json()
    assert me["name"] == "Studio Luna"
    assert client.post("/api/v1/auth/register", json={"email": "MODEL@example.com", "password": "correct-horse-1",
                                                      "tenant_name": "x"}).status_code == 409
    r = client.post("/api/v1/auth/login", json={"email": "Model@Example.com", "password": "correct-horse-1"})
    assert r.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "model@example.com", "password": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=H(tok)).json()["email"] == "model@example.com"


def test_short_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "short", "tenant_name": "x"})
    assert r.status_code == 422


def test_lockout_after_failed_logins(client):
    signup(client, "lock@example.com")
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": "wrong"})
    r = client.post("/api/v1/auth/login", json={"email": "lock@example.com", "password": "correct-horse-1"})
    assert r.status_code == 429


def test_refresh_and_logout_everywhere(client):
    tok = signup(client, "r@example.com")
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert client.get("/api/v1/tenants/me", headers=H(new)).status_code == 200
    # a refresh token is never accepted as an access token
    assert client.get("/api/v1/tenants/me",
                      headers={"Authorization": f"Bearer {tok['refresh_token']}"}).status_code == 401
    assert client.post("/api/v1/auth/logout-all", headers=H(new)).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_delete_account_requires_fresh_password(client, monkeypatch):
    tok = signup(client, "del@example.com", "Del Studio")
    old = sec.issue_token
    stale = old(str(client.get("/api/v1/auth/me", headers=H(tok)).json()["id"]), tok["tenant_id"], ["owner"],
                auth_time=int(time.time()) - 3600)
    r = client.request("DELETE", "/api/v1/tenants/me", headers={"Authorization": f"Bearer {stale}",
                                                                 "X-Confirm-Delete": "Del Studio"})
    assert r.status_code == 401
    assert client.post("/api/v1/auth/reauth", headers={"Authorization": f"Bearer {stale}"},
                       json={"password": "wrong"}).status_code == 401
    fresh = client.post("/api/v1/auth/reauth", headers={"Authorization": f"Bearer {stale}"},
                        json={"password": "correct-horse-1"}).json()
    r = client.request("DELETE", "/api/v1/tenants/me", headers={**H(fresh), "X-Confirm-Delete": "Del Studio"})
    assert r.status_code == 200, r.text
    assert client.post("/api/v1/auth/login", json={"email": "del@example.com",
                                                   "password": "correct-horse-1"}).status_code == 401


def test_team_members_and_isolation(client):
    owner = signup(client, "own@example.com", "Agency")
    r = client.post("/api/v1/auth/team", headers=H(owner),
                    json={"email": "agent@example.com", "password": "agent-pass-123", "role": "agent"})
    assert r.status_code == 201
    agent = client.post("/api/v1/auth/login", json={"email": "agent@example.com", "password": "agent-pass-123"}).json()
    assert agent["role"] == "agent" and agent["tenant_id"] == owner["tenant_id"]
    assert client.get("/api/v1/chat/inbox", headers=H(agent)).status_code == 200
    assert client.post("/api/v1/auth/team", headers=H(agent),
                       json={"email": "x@example.com", "password": "agent-pass-123"}).status_code == 403
    assert client.post("/api/v1/auth/team", headers=H(owner),
                       json={"email": "o2@example.com", "password": "agent-pass-123", "role": "owner"}).status_code == 422
    other = signup(client, "other@example.com", "Other")
    member_id = r.json()["id"]
    assert client.delete(f"/api/v1/auth/team/{member_id}", headers=H(other)).status_code == 404
    assert [m["email"] for m in client.get("/api/v1/auth/team", headers=H(other)).json()] == ["other@example.com"]
    assert client.delete(f"/api/v1/auth/team/{member_id}", headers=H(owner)).status_code == 204


def test_billing_checkout(client, monkeypatch):
    from apps.api.routers import billing
    from apps.core.config import settings
    tok = signup(client, "pay@example.com", "Pay")
    assert client.post("/api/v1/billing/checkout", headers=H(tok), json={"tier": "pro"}).status_code in (422, 503)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_123")
    seen = {}

    async def fake(path, form):
        seen["path"], seen["form"] = path, dict(form)
        return {"url": "https://checkout.stripe.com/c/pay/cs_test"}

    monkeypatch.setattr(billing, "_stripe", fake)
    r = client.post("/api/v1/billing/checkout", headers=H(tok), json={"tier": "pro"})
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    assert seen["form"]["subscription_data[metadata][tenant_id]"] == tok["tenant_id"]
    assert seen["form"]["subscription_data[metadata][tier]"] == "pro"
    assert client.post("/api/v1/billing/portal", headers=H(tok)).status_code == 404


def test_removed_member_and_logout_all_invalidate_access_tokens(client):
    owner = signup(client, "boss@example.com", "Boss")
    r = client.post("/api/v1/auth/team", headers=H(owner),
                    json={"email": "temp@example.com", "password": "agent-pass-123", "role": "agent"})
    agent = client.post("/api/v1/auth/login", json={"email": "temp@example.com", "password": "agent-pass-123"}).json()
    assert client.get("/api/v1/chat/inbox", headers=H(agent)).status_code == 200
    client.delete(f"/api/v1/auth/team/{r.json()['id']}", headers=H(owner))
    assert client.get("/api/v1/chat/inbox", headers=H(agent)).status_code == 401  # immediately, not after 15 min
    assert client.post("/api/v1/auth/logout-all", headers=H(owner)).status_code == 204
    assert client.get("/api/v1/tenants/me", headers=H(owner)).status_code == 401
