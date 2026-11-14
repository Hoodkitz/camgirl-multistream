"""Browser e2e (Playwright, headless) against a real uvicorn process and a local Stripe fake.

No real Stripe key, network or cost: STRIPE_API_BASE (dev/test only) points billing at a local fake server.
Skipped automatically when playwright / a chromium build is not installed (e.g. plain CI `pytest`).
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import httpx
import pytest

sync_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]
PW = "Correct-horse-1A"


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeStripe(BaseHTTPRequestHandler):
    seen: ClassVar[list[tuple[str, str, str]]] = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        type(self).seen.append((self.path, self.headers.get("Authorization", ""), body))
        out = json.dumps({"id": "cs_test_fake", "url": f"http://127.0.0.1:{self.server.server_port}/pay/cs_test_fake"})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>FAKE STRIPE CHECKOUT</body></html>")


@pytest.fixture(scope="module")
def stack():
    _FakeStripe.seen = []
    stripe = HTTPServer(("127.0.0.1", 0), _FakeStripe)
    threading.Thread(target=stripe.serve_forever, daemon=True).start()
    port, tmp = _port(), tempfile.mkdtemp()
    env = {**os.environ, "ENV": "test", "DATABASE_URL": f"sqlite+aiosqlite:///{tmp}/e2e.db",
           "KEY_STORE_DIR": f"{tmp}/keys", "JWT_SECRET": "e2e-secret-0123456789abcdef0123456789",
           "RATE_LIMIT_PER_MINUTE": "1000", "PUBLIC_BASE_URL": f"http://127.0.0.1:{port}",
           "STRIPE_SECRET_KEY": "sk_test_local_fake_not_a_real_key", "STRIPE_PRICE_PRO": "price_test_pro",
           "STRIPE_API_BASE": f"http://127.0.0.1:{stripe.server_port}/v1"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "apps.api.main:app", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.fail("server did not start")
        yield base, _FakeStripe
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:  # uvicorn waits for open keep-alive connections
            proc.kill()
            proc.wait(5)
        stripe.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except (sync_api.Error, OSError) as e:  # browser binaries missing
            pytest.skip(f"chromium unavailable: {e}")
        yield b
        b.close()


def test_register_login_team_checkout(stack, browser):
    base, fake = stack
    name, email = f"Studio {uuid.uuid4().hex[:6]}", f"owner-{uuid.uuid4().hex[:6]}@example.com"
    page = browser.new_page()
    page.set_default_timeout(8000)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    # 1. Registration through the UI
    page.goto(f"{base}/app/")
    page.click("button[data-i18n=register_tab]")
    page.fill("#reg-name", name)
    page.fill("#reg-email", email)
    page.fill("#reg-password", PW)
    page.click("#register-form button[type=submit]")
    page.wait_for_selector("#main-section.active", timeout=10000)

    # 2. Logout, then login through the UI
    page.click("[data-i18n=logout]")
    page.wait_for_selector("#auth-section.active")
    page.fill("#login-email", email)
    page.fill("#login-password", PW)
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#main-section.active", timeout=10000)

    # 3. Main flows navigation: every view renders without JS errors
    for view in ("chat", "automation", "stats", "settings", "dashboard"):
        page.click(f".nav-btn[onclick*=\"'{view}'\"]")
        page.wait_for_selector(f"#view-{view}.active")

    # 4. Dashboard flows: stream key create & revoke, platform credentials
    page.click(".nav-btn[onclick*=\"'dashboard'\"]")
    page.fill("#sk-label", "Main OBS Key")
    page.click("#view-dashboard form:has(#sk-label) button[type=submit]")
    page.wait_for_selector("#new-stream-key-result:not(.hidden)", timeout=5000)
    page.wait_for_selector("#stream-keys-list li:has-text('Main OBS Key')")
    page.click("#stream-keys-list li:has-text('Main OBS Key') button")
    page.wait_for_selector("#stream-keys-list li:has-text('(Revoked)')", timeout=5000)

    page.fill("#cred-username", "testcreator_cam")
    page.fill("#cred-streamkey", "secret-stream-token")
    page.click("#view-dashboard form:has(#cred-username) button[type=submit]")
    page.wait_for_selector("#credentials-list li:has-text('testcreator_cam')", timeout=5000)

    # 5. Automation settings flow
    page.click(".nav-btn[onclick*=\"'automation'\"]")
    page.check("#auto-greet-enabled")
    page.fill("#auto-greet-template", "Welcome {username} to {platform}!")
    page.fill("#auto-tip-goal", "1000")
    page.click("#automation-form button[type=submit]")

    # 6. Team management flow: add agent via UI, verify login via API, remove agent via UI
    page.click(".nav-btn[onclick*=\"'settings'\"]")
    page.wait_for_selector("#view-settings.active")
    agent_email = f"agent-{uuid.uuid4().hex[:6]}@example.com"
    page.fill("#team-email", agent_email)
    page.fill("#team-password", PW)
    page.select_option("#team-role", "agent")
    page.click("#team-form button[type=submit]")
    page.wait_for_selector(f"#team-members-list li:has-text('{agent_email}')", timeout=5000)

    # Agent can log in
    api = httpx.Client(base_url=base)
    agent_resp = api.post("/api/v1/auth/login", json={"email": agent_email, "password": PW})
    assert agent_resp.status_code == 200, agent_resp.text

    # Owner removes agent via UI
    page.click(f"#team-members-list li:has-text('{agent_email}') button")
    page.wait_for_selector(f"#team-members-list li:has-text('{agent_email}')", state="detached", timeout=5000)

    # Removed agent can no longer log in
    assert api.post("/api/v1/auth/login", json={"email": agent_email, "password": PW}).status_code == 401

    # 7. Language toggle flow
    page.click("#lang-btn")
    assert page.text_content("#lang-btn") == "EN"
    page.click("#lang-btn")
    assert page.text_content("#lang-btn") == "DE"

    # 8. Stripe checkout (test mode, local fake) -> browser is redirected to the checkout URL
    page.click("[data-i18n=upgrade_pro]")
    page.wait_for_url("**/pay/cs_test_fake", timeout=10000)
    assert "FAKE STRIPE CHECKOUT" in page.content()
    path, _authz, body = fake.seen[-1]
    assert path == "/v1/checkout/sessions" and "price_test_pro" in body and "mode=subscription" in body
    assert not errors, errors
    page.close()
