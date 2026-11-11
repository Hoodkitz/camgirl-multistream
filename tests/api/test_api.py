import json
import time
import uuid
from datetime import datetime, timezone

from apps.domain.signing import sign
from apps.services import connectors
from tests.conftest import CONN, SRS, auth


def add_cred(client, H, platform="stripchat", user="luna", key="SC-STREAMKEY-123"):
    r = client.post("/api/v1/credentials", headers=H("owner"),
                    json={"platform": platform, "account_username": user, "stream_key": key, "api_token": "tok"})
    assert r.status_code == 201, r.text
    return r.json()


def event(tid, eid, etype="message", platform="stripchat", **payload):
    return {"event_id": eid, "tenant_id": tid, "platform": platform, "event_type": etype,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sender": {"platform_user_id": "usr_1", "username": "VipDonor99"}, "payload": payload}


def test_health(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_credentials_werden_nie_im_klartext_geliefert(client, tenant):
    tid, H = tenant
    acc = add_cred(client, H)
    assert "stream_key" not in acc and "SC-STREAMKEY" not in json.dumps(acc)
    listed = client.get("/api/v1/credentials", headers=H("agent"))
    assert listed.status_code == 403  # Agent darf Konten nicht sehen
    assert client.get("/api/v1/credentials", headers=H("creator")).json()[0]["platform"] == "stripchat"
    assert client.post("/api/v1/credentials", headers=H("owner"), json={
        "platform": "stripchat", "account_username": "luna", "stream_key": "xxxx"}).status_code == 409


def test_stream_flow_srs_callbacks_und_quota(client, tenant):
    tid, H = tenant
    add_cred(client, H, "stripchat", "luna", "SC-KEY-1")
    add_cred(client, H, "chaturbate", "luna_cb", "CB-KEY-2")
    sk = client.post("/api/v1/streams/keys", headers=H("creator"), json={"label": "OBS"}).json()
    assert sk["stream_key"].startswith("sk_") and sk["rtmp_url"].endswith(sk["stream_key"])

    # falsches Secret / falscher Key
    hook = {"action": "on_publish", "client_id": "c1", "stream": sk["stream_key"]}
    assert client.post("/api/v1/streams/verify", json=hook).status_code == 401
    assert client.post("/api/v1/streams/verify", headers=SRS, json={**hook, "stream": "sk_falsch"}).status_code == 403

    assert client.post("/api/v1/streams/verify", headers=SRS, json=hook).json() == {"code": 0}
    fwd = client.post("/api/v1/streams/verify", headers=SRS, json={**hook, "action": "on_forward"}).json()
    urls = fwd["data"]["urls"]
    assert any(u.endswith("/SC-KEY-1") and u.startswith("rtmp://s-sd.stripst.com") for u in urls)
    assert any(u.endswith("/CB-KEY-2") for u in urls)

    # Standard-Tarif: nur 1 paralleler Feed
    assert client.post("/api/v1/streams/verify", headers=SRS, json={**hook, "client_id": "c2"}).status_code == 429

    # Creator sieht maskierte Ziele
    t = client.get("/api/v1/streams/targets", headers=H("creator")).json()
    assert all("SC-KEY-1" not in x["url"] and "CB-KEY-2" not in x["url"] for x in t)

    assert client.post("/api/v1/streams/verify", headers=SRS, json={**hook, "action": "on_unpublish"}).json()["code"] == 0
    s = client.get("/api/v1/streams/sessions", headers=H("owner")).json()
    assert s[0]["end_reason"] == "unpublish" and set(s[0]["targets"]) == {"stripchat", "chaturbate"}

    # Widerrufener Key
    client.delete(f"/api/v1/streams/keys/{sk['id']}", headers=H("owner"))
    assert client.post("/api/v1/streams/verify", headers=SRS, json=hook).status_code == 403


def test_target_quota_standard_max_3(client, tenant):
    tid, H = tenant
    for i, p in enumerate(["stripchat", "chaturbate", "bongacams", "camsoda"]):
        add_cred(client, H, p, f"acc{i}", f"KEY-{i}")
    assert len(client.get("/api/v1/streams/targets", headers=H("owner")).json()) == 3


def test_chat_ingest_idempotent_inbox_und_replay(client, tenant):
    tid, H = tenant
    add_cred(client, H)
    assert client.post("/api/v1/events", json=event(tid, "e1", message="Hi")).status_code == 401
    assert client.post("/api/v1/events", headers=CONN, json=event(tid, "e1", message="Hi")).json()["status"] == "accepted"
    assert client.post("/api/v1/events", headers=CONN, json=event(tid, "e1", message="Hi")).json()["status"] == "duplicate"
    client.post("/api/v1/events", headers=CONN, json=event(tid, "e2", platform="chaturbate", message="Hallo"))
    inbox = client.get("/api/v1/chat/inbox", headers=H("agent")).json()
    assert [e["message"] for e in inbox] == ["Hi", "Hallo"]
    sc = client.get("/api/v1/chat/inbox?platform=stripchat", headers=H("agent")).json()
    assert len(sc) == 1
    replay = client.get(f"/api/v1/chat/inbox?since_id={inbox[0]['id']}", headers=H("agent")).json()
    assert [e["event_id"] for e in replay] == ["e2"]
    tabs = client.get("/api/v1/chat/tabs", headers=H("agent")).json()
    assert tabs[0]["platform"] == "stripchat" and tabs[0]["messages_24h"] == 1


def test_reply_ueber_outbox_mit_entschluesselten_credentials(client, tenant):
    tid, H = tenant
    add_cred(client, H)
    assert client.post("/api/v1/chat/reply", headers=H("agent"),
                       json={"platform": "chaturbate", "text": "x"}).status_code == 409
    r = client.post("/api/v1/chat/reply", headers=H("agent"), json={"platform": "stripchat", "text": "Danke dir! 😘"})
    assert r.status_code == 202
    sent = connectors.connector.sent
    assert sent == [{"platform": "stripchat", "account": "luna", "recipient": None, "text": "Danke dir! 😘"}]
    out = client.get("/api/v1/chat/inbox", headers=H("agent")).json()
    assert out[-1]["is_outgoing"] and not out[-1]["is_automated"]


def test_auto_begruessung_mit_cooldown(client, tenant):
    tid, H = tenant
    add_cred(client, H)
    r = client.put("/api/v1/automation", headers=H("creator"), json={
        "greet_enabled": True, "greet_template": "Hey {username}, schön dass du da bist!", "greet_cooldown_hours": 24})
    assert r.status_code == 200
    res = client.post("/api/v1/events", headers=CONN, json=event(tid, "j1", "join")).json()
    assert res["actions"] == ["greeting_queued"]
    assert connectors.connector.sent[0]["text"] == "Hey VipDonor99, schön dass du da bist!"
    assert client.post("/api/v1/events", headers=CONN, json=event(tid, "j2", "join")).json()["actions"] == []
    assert len(connectors.connector.sent) == 1
    inbox = client.get("/api/v1/chat/inbox", headers=H("owner")).json()
    assert [e["message"] for e in inbox if e["is_automated"]] == ["Hey VipDonor99, schön dass du da bist!"]


def test_spendenziel_loest_obs_outbox_aus(client, tenant):
    tid, H = tenant
    add_cred(client, H)
    client.put("/api/v1/automation", headers=H("owner"), json={
        "tip_goal_tokens": 1000, "tip_goal_label": "Tanz", "obs_webhook_url": "https://obs.example.invalid/hook"})
    sk = client.post("/api/v1/streams/keys", headers=H("owner"), json={}).json()
    client.post("/api/v1/streams/verify", headers=SRS, json={"action": "on_publish", "client_id": "c1", "stream": sk["stream_key"]})
    assert client.post("/api/v1/events", headers=CONN, json=event(tid, "t1", "tip", tokens_spent=600, fiat_equivalent_usd=30)).json()["actions"] == []
    assert client.post("/api/v1/events", headers=CONN, json=event(tid, "t2", "tip", tokens_spent=500, fiat_equivalent_usd=25)).json()["actions"] == ["goal_reached"]
    assert client.post("/api/v1/events", headers=CONN, json=event(tid, "t3", "tip", tokens_spent=10)).json()["actions"] == []
    s = client.get("/api/v1/streams/sessions", headers=H("owner")).json()[0]
    assert s["tip_total"] == 1110 and s["goal_reached"]
    # OBS-Ziel ist nicht erreichbar -> Outbox bleibt PENDING mit Backoff (kein Absturz)


def test_stats(client, tenant):
    tid, H = tenant
    client.post("/api/v1/events", headers=CONN, json=event(tid, "t1", "tip", tokens_spent=500, fiat_equivalent_usd=25))
    client.post("/api/v1/events", headers=CONN, json=event(tid, "t2", "tip", platform="chaturbate", tokens_spent=100, fiat_equivalent_usd=5))
    client.post("/api/v1/events", headers=CONN, json=event(tid, "m1", message="hi"))
    st = client.get("/api/v1/stats/overview", headers=H("audit")).json()
    assert st["umsatz_usd_gesamt"] == 30
    assert st["plattformen"]["stripchat"]["top_spender"] == [{"name": "VipDonor99", "tokens": 500}]
    assert st["plattformen"]["stripchat"]["aktive_chatter"] == 1


def test_websocket_ticket_und_live_event(client, tenant):
    tid, H = tenant
    t = client.post("/api/v1/ws/ticket", headers=H("agent")).json()["ticket"]
    with client.websocket_connect(f"/ws/v1/chat?ticket={t}") as ws:
        client.post("/api/v1/events", headers=CONN, json=event(tid, "live1", message="Live!"))
        msg = ws.receive_json()
        assert msg["type"] == "chat_event" and msg["event"]["message"] == "Live!"
    # Ticket ist einmalig
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/v1/chat?ticket={t}") as ws:
            ws.receive_json()


def test_stripe_webhook_signatur_idempotenz_und_tier(client, tenant):
    tid, H = tenant
    ev = {"id": "evt_1", "type": "customer.subscription.updated",
          "data": {"object": {"status": "active", "customer": "cus_1", "metadata": {"tenant_id": tid, "tier": "agency"}}}}
    body = json.dumps(ev).encode()
    assert client.post("/api/v1/webhooks/stripe", content=body, headers={"Stripe-Signature": "t=1,v1=x"}).status_code == 400
    hdr = {"Stripe-Signature": sign("whsec_dev", body), "Content-Type": "application/json"}
    assert client.post("/api/v1/webhooks/stripe", content=body, headers=hdr).json()["status"] == "accepted"
    assert client.post("/api/v1/webhooks/stripe", content=body, headers=hdr).json()["status"] == "duplicate"
    assert client.get("/api/v1/tenants/me", headers=H("owner")).json()["tier"] == "agency"


def test_mandantentrennung(client, tenant):
    tid, H = tenant
    add_cred(client, H)
    client.post("/api/v1/events", headers=CONN, json=event(tid, "e1", message="privat"))
    other = str(uuid.uuid4())
    O = lambda *r: auth(other, *r)  # noqa: E731
    assert client.get("/api/v1/chat/inbox", headers=O("owner")).json() == []
    assert client.get("/api/v1/credentials", headers=O("owner")).json() == []
    acc_id = client.get("/api/v1/credentials", headers=H("owner")).json()[0]["id"]
    assert client.delete(f"/api/v1/credentials/{acc_id}", headers=O("owner")).status_code == 404
    assert client.get("/api/v1/stats/overview", headers=O("owner")).json()["umsatz_usd_gesamt"] == 0


def test_dsgvo_loeschung_mit_reauth_und_crypto_shredding(client, tenant):
    tid, H = tenant
    add_cred(client, H)
    alt = H("owner", auth_time=int(time.time()) - 3600)
    assert client.delete("/api/v1/tenants/me", headers={**alt, "X-Confirm-Delete": "Luna Studio"}).status_code == 401
    assert client.delete("/api/v1/tenants/me", headers={**H("owner"), "X-Confirm-Delete": "falsch"}).status_code == 422
    assert client.delete("/api/v1/tenants/me", headers={**H("creator"), "X-Confirm-Delete": "Luna Studio"}).status_code == 403
    r = client.delete("/api/v1/tenants/me", headers={**H("owner"), "X-Confirm-Delete": "Luna Studio"})
    assert r.status_code == 200 and r.json()["crypto_shredded"]
    import os
    assert not [f for f in os.listdir(os.environ["KEY_STORE_DIR"]) if tid in f]
    assert client.get("/api/v1/tenants/me", headers=H("owner")).status_code == 404
    assert client.get("/api/v1/credentials", headers=H("owner")).json() == []


def test_rate_limit_429():
    from apps.api import main
    old = main.limiter
    main.limiter = main.TokenBucket(capacity=2, refill_per_sec=0.001)
    try:
        from fastapi.testclient import TestClient
        with TestClient(main.app) as c:
            h = auth(uuid.uuid4(), "owner")
            codes = [c.get("/api/v1/tenants/me", headers=h).status_code for _ in range(3)]
            assert codes[:2] == [404, 404] and codes[2] == 429
    finally:
        main.limiter = old


def test_ssrf_schutz(client, tenant):
    tid, H = tenant
    for url in ("http://obs.example.com/x", "https://127.0.0.1/x", "https://10.0.0.5/x", "https://localhost/x",
                "https://[::1]/x", "https://169.254.169.254/latest"):
        assert client.put("/api/v1/automation", headers=H("owner"), json={"obs_webhook_url": url}).status_code == 422, url
    for url in ("rtmp://10.0.0.1/live", "rtmp://evil.example.com/live", "http://s-sd.stripst.com/ext",
                "rtmp://s-sd.stripst.com:22/ext"):
        r = client.post("/api/v1/credentials", headers=H("owner"), json={
            "platform": "stripchat", "account_username": "x", "stream_key": "abcd", "ingest_url": url})
        assert r.status_code == 422, url
    ok = client.post("/api/v1/credentials", headers=H("owner"), json={
        "platform": "stripchat", "account_username": "x", "stream_key": "abcd", "ingest_url": "rtmp://s-sd.stripst.com/ext"})
    assert ok.status_code == 201


def test_netguard_beim_senden():
    import pytest

    from apps.domain.netguard import assert_public_host
    with pytest.raises(ValueError):
        assert_public_host("127.0.0.1")
    with pytest.raises(ValueError):
        assert_public_host("localhost")
    assert assert_public_host("1.1.1.1") == ["1.1.1.1"]
