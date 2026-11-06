"""Browser end-to-end tests: FastAPI serving the built React app, driven by Playwright.

Every test signs in through the real email-code flow; the server runs with console
email delivery and development codes shown on screen.

Requires `npm run build` in frontend/ and Playwright's Chromium. Skipped otherwise.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

import src.api.server as server
from tests.integration.auth_helpers import ADMIN, make_auth

playwright_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

pytestmark = pytest.mark.skipif(not (server.FRONTEND_DIST / "index.html").exists(),
                                reason="frontend not built (run: cd frontend && npm ci && npm run build)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    import os

    os.environ["CONTENTBLITZ_OUTPUT_DIR"] = str(tmp_path_factory.mktemp("out"))
    app = server.create_app({"app": {"use_mock": True, "max_retries": 0}}, env="test",
                            auth=make_auth(expose_dev_codes=True))
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium unavailable: {exc}")
        yield b
        b.close()


def _new_page(browser, base_url, width=1280, height=900):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    pg = ctx.new_page()
    # Fonts come from Google; block them so tests never depend on the network.
    pg.route("**/fonts.{googleapis,gstatic}.com/**", lambda r: r.abort())
    pg.goto(base_url)
    pg.wait_for_selector(".auth__form")
    return ctx, pg


def _enter_code(pg):
    code = pg.locator(".auth__dev code").inner_text()
    pg.get_by_label("Digit 1").fill(code)


def sign_up(pg, email, name):
    pg.get_by_role("button", name="Sign up", exact=True).click()
    pg.get_by_label("Your name").fill(name)
    pg.get_by_label("Email").fill(email)
    pg.get_by_role("button", name="Create account").click()
    _enter_code(pg)
    pg.wait_for_selector(".chat__empty")


_counter = iter(range(10_000))


@pytest.fixture
def page(browser, base_url):
    ctx, pg = _new_page(browser, base_url)
    sign_up(pg, f"writer{next(_counter)}@example.com", "Wren Writer")
    yield pg
    ctx.close()


def test_login_rejects_unregistered_email_then_signup_and_login_with_codes(browser, base_url):
    expect = playwright_api.expect
    ctx, pg = _new_page(browser, base_url)
    box = pg.locator(".auth__form").bounding_box()
    assert abs((box["x"] + box["width"] / 2) - 640) < 4  # centred horizontally
    assert 200 < box["y"] + box["height"] / 2 < 700       # and vertically in the first screen
    playwright_api.expect(pg.get_by_text("Log in or create an account")).to_be_visible()

    pg.get_by_label("Email").fill("newbie@example.com")
    pg.get_by_role("button", name="Continue").click()
    expect(pg.get_by_role("alert")).to_contain_text("newbie@example.com isn't registered")
    pg.get_by_role("button", name="Sign up with this email").click()
    pg.get_by_label("Your name").fill("Nia Newbie")
    pg.get_by_role("button", name="Create account").click()
    expect(pg.get_by_role("heading", name="Check your email")).to_be_visible()
    _enter_code(pg)
    expect(pg.locator(".account__name")).to_have_text("Nia Newbie")
    expect(pg.get_by_role("button", name="New conversation", exact=False).first).to_be_visible()

    pg.get_by_role("button", name="Sign out").click()
    pg.get_by_label("Email").fill("newbie@example.com")
    pg.get_by_role("button", name="Continue").click()
    _enter_code(pg)
    expect(pg.locator(".account__email")).to_have_text("newbie@example.com")
    ctx.close()


def test_campaign_flow_fills_every_panel(page):
    expect = playwright_api.expect
    page.get_by_role("button", name="Create a full campaign about B2B podcast marketing").click()
    expect(page.locator(".msg--assistant")).to_contain_text("Research on B2B podcast marketing", timeout=30000)
    expect(page.locator(".msg__agents").last).to_contain_text("research")
    expect(page.locator(".pipeline")).to_have_count(0)  # no progress strip above the tabs
    expect(page.locator(".msg__image")).to_be_visible()

    page.get_by_role("tab", name="Content").click()
    expect(page.locator(".editor__head h2")).to_contain_text("B2B Podcast Marketing")
    article = page.get_by_label("Article (Markdown)")
    article.fill("# Edited title\n\nShort.")
    page.get_by_role("button", name="Save and re-score").click()
    expect(page.locator(".savebar__msg")).to_contain_text("Saved and re-scored.")

    page.get_by_role("tab", name="Research").click()
    expect(page.locator(".research__sources li")).to_have_count(10)

    page.get_by_role("tab", name="Export").click()
    with page.expect_download() as dl:
        page.get_by_role("link", name="Markdown").first.click()
    assert dl.value.suggested_filename.endswith(".md")


def test_followup_refines_previous_piece_and_survives_reload(page):
    expect = playwright_api.expect
    box = page.get_by_label("Message")
    box.fill("Write a LinkedIn post about hybrid work")
    box.press("Enter")
    expect(page.locator(".msg--assistant")).to_have_count(1, timeout=30000)
    box.fill("make it more formal")
    box.press("Enter")
    expect(page.locator(".msg--assistant").nth(1)).to_contain_text("revised the **linkedin**".replace("**", ""), timeout=30000)
    page.reload()
    expect(page.locator(".msg")).to_have_count(4)  # still signed in; thread restored from memory
    expect(page.locator(".thread--active .thread__title")).to_have_text("Write a LinkedIn post about hybrid work")

    page.get_by_role("button", name="New conversation", exact=False).first.click()
    expect(page.locator(".chat__empty")).to_be_visible()
    page.locator(".thread__open", has_text="Write a LinkedIn post").click()
    expect(page.locator(".msg")).to_have_count(4)


def test_mobile_menu_drawer_and_no_horizontal_scroll(browser, base_url):
    ctx, pg = _new_page(browser, base_url, 390, 844)
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    sign_up(pg, "mobile@example.com", "Mo Bile")
    sidebar = pg.locator(".sidebar")
    assert not sidebar.evaluate("e => e.getBoundingClientRect().right > 0")
    pg.get_by_role("button", name="Menu", exact=True).click()
    playwright_api.expect(pg.get_by_role("button", name="Close menu")).to_be_visible()
    playwright_api.expect(pg.locator(".account__name")).to_have_text("Mo Bile")
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    ctx.close()


def test_admin_dashboard_is_only_for_admins(browser, base_url):
    expect = playwright_api.expect
    ctx, pg = _new_page(browser, base_url)
    sign_up(pg, "customer@example.com", "Cus Tomer")
    expect(pg.get_by_role("link", name="Admin dashboard")).to_have_count(0)
    pg.goto(base_url + "/admin")
    expect(pg.get_by_role("heading", name="This page is for administrators")).to_be_visible()
    ctx.close()

    ctx, pg = _new_page(browser, base_url)
    sign_up(pg, ADMIN, "Ada Admin")
    pg.get_by_role("link", name="Admin dashboard").click()
    expect(pg.get_by_role("heading", name="Server dashboard")).to_be_visible()
    expect(pg.get_by_role("heading", name="Usage since the server started")).to_be_visible()
    expect(pg.get_by_label("Offline mode")).to_be_checked()
    pg.get_by_role("button", name="Save settings").click()
    expect(pg.locator(".toast")).to_contain_text("Settings saved")
    expect(pg.locator(".admin table")).to_contain_text("customer@example.com")
    ctx.close()
