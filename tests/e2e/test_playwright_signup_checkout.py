import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"


def test_signup_and_checkout():
    name = f"TestStudio_{int(time.time())}"
    email = f"{name.lower()}@example.invalid"
    password = "correct-horse-1"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE}/app")
        # Switch to register tab
        page.click(".tab-btn[onclick*='register']")
        page.fill("#reg-name", name)
        page.fill("#reg-email", email)
        page.fill("#reg-password", password)
        page.click("#register-form button[type=submit]")
        # after register the main app should show
        page.wait_for_selector("#user-info")
        assert name in page.inner_text("#user-info")
        # go to settings and click upgrade
        page.click(".nav-btn[onclick*='settings']")
        page.wait_for_selector("#subscription-status")
        # Click upgrade and expect navigation to stripe checkout domain
        with page.expect_navigation(timeout=5000):
            # button has data-i18n or onclick
            # try the i18n button first
            try:
                page.click("button[data-i18n='upgrade_pro']")
            except Exception:
                page.click(".btn[onclick*='checkoutStripe']")
        # The URL should be the fake stripe checkout url we return from the server
        assert page.url.startswith("https://checkout.stripe.com/")
        browser.close()
