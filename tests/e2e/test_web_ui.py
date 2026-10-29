"""Browser end-to-end tests: FastAPI serving the built React app, driven by Playwright.

Requires `npm run build` in frontend/ and Playwright's Chromium. Skipped otherwise.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

import src.api.server as server

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
    app = server.create_app({"app": {"use_mock": True, "max_retries": 0}}, env="test")
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


@pytest.fixture
def page(browser, base_url):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    # Fonts come from Google; block them so tests never depend on the network.
    pg.route("**/fonts.{googleapis,gstatic}.com/**", lambda r: r.abort())
    pg.goto(base_url)
    pg.wait_for_selector(".chat__empty")
    yield pg
    ctx.close()


def test_campaign_flow_streams_pipeline_and_fills_every_panel(page):
    expect = playwright_api.expect
    page.get_by_role("button", name="Create a full campaign about B2B podcast marketing").click()
    expect(page.locator(".msg--assistant")).to_contain_text("Research on B2B podcast marketing", timeout=30000)
    expect(page.locator(".station--ok")).to_have_count(6)
    expect(page.locator(".msg__image")).to_be_visible()

    page.get_by_role("tab", name="Content").click()
    expect(page.locator(".editor__head h2")).to_contain_text("B2B Podcast Marketing")
    article = page.get_by_label("Article (Markdown)")
    article.fill("# Edited title\n\nShort.")
    page.get_by_role("button", name="Save and re-score").click()
    expect(page.get_by_role("status")).to_contain_text("Saved and re-scored.")

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
    expect(page.locator(".msg")).to_have_count(4)  # thread restored from memory


def test_mobile_settings_drawer(browser, base_url):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.route("**/fonts.{googleapis,gstatic}.com/**", lambda r: r.abort())
    pg.goto(base_url)
    sidebar = pg.locator(".sidebar")
    assert not sidebar.evaluate("e => e.getBoundingClientRect().right > 0")
    pg.get_by_role("button", name="Settings", exact=True).click()
    playwright_api.expect(pg.get_by_role("button", name="Close settings")).to_be_visible()
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    ctx.close()
