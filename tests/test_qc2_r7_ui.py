"""
The image provider setting and the Generate outcome, as a creator sees them.
[R7, BE-06]

Driven in headless Chromium against the built UI and an in-process studio,
with service workers blocked. Every image provider answers from the fake on
127.0.0.1 (tests/qc2_r7_fake_images.py), behind the socket guard, so no real
image service is ever called.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import uvicorn  # noqa: E402

import qc2_r7_fake_images as fakes  # noqa: E402

FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
pytestmark = pytest.mark.skipif(not os.path.exists(FRONTEND), reason="the studio UI is not built")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def fake():
    server = fakes.FakeImageServer().start()
    yield server
    server.stop()


@pytest.fixture(scope="module")
def studio_url(fake):
    patch = pytest.MonkeyPatch()
    fakes.install_socket_guard(patch)
    for name in ("INOX_NO_EGRESS", "INOX_ALLOW_IMAGE_EGRESS", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        patch.delenv(name, raising=False)
    home = tempfile.mkdtemp(prefix="inox_qc2_r7_ui_")
    patch.setenv("INOX_HYDRA_HOME", home)

    from app import app
    from database import init_db

    init_db()
    for name, module in list(sys.modules.items()):
        if name.rsplit(".", 1)[-1] == "image_providers" and module:
            patch.setattr(module, "ENDPOINTS", {k: fake.url(k) for k in module.ENDPOINTS})

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    patch.undo()
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser, studio_url, fake):
    import image_providers
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(provider="local_deterministic")
    image_providers.save("pollinations")
    fake.fail.clear()
    fake.requests.clear()
    context = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    tab = context.new_page()
    tab.goto(studio_url, wait_until="networkidle")
    yield tab
    context.close()


def _open_inspector_tab(page, name):
    page.click('button[aria-label="Composer"]')
    opener = page.locator('button[aria-label="Open inspector"]')
    if opener.count() and opener.is_visible():
        opener.click()
    page.click(f'aside[aria-label="Inspector"] button:has-text("{name}")')
    return page.locator('aside[aria-label="Inspector"]')


def test_the_prompt_tab_shows_the_image_provider_and_what_leaves(page):
    panel = _open_inspector_tab(page, "Prompt")
    page.wait_for_selector("text=Change image provider")
    text = panel.inner_text()
    assert "Free public generator (image.pollinations.ai)" in text
    assert "SENDS THE PROMPT OUT" in text
    assert "a free public service run by a third party" in text


def test_choosing_openai_shows_what_leaves_before_saving_then_checks_the_key(page, fake):
    panel = _open_inspector_tab(page, "Prompt")
    page.wait_for_selector("text=Change image provider")
    page.select_option('select[aria-label="Image provider"]', "openai")

    # Said before anything is saved or sent.
    assert "api.openai.com (OpenAI)." in panel.inner_text()
    assert fake.requests == []

    page.fill('input[aria-label="Image provider API key"]', fakes.GOOD_KEY)
    page.click('section[aria-label="Image provider settings"] button:has-text("Verify and save")')
    page.wait_for_selector("text=OpenAI accepted the key. Model: gpt-image-1.")

    text = panel.inner_text()
    assert "..." + fakes.GOOD_KEY[-4:] in text
    assert fakes.GOOD_KEY not in text
    assert page.input_value('input[aria-label="Image provider API key"]') == ""


def test_a_refused_key_is_said_where_it_was_typed(page):
    panel = _open_inspector_tab(page, "Prompt")
    page.wait_for_selector("text=Change image provider")
    page.select_option('select[aria-label="Image provider"]', "stability")
    page.fill('input[aria-label="Image provider API key"]', "sk-notarealkey-r7-wrong-000000000000")
    page.click('section[aria-label="Image provider settings"] button:has-text("Verify and save")')
    page.wait_for_selector("text=refused the key (HTTP 401)")
    assert "sk-notarealkey-r7-wrong" not in panel.inner_text()


def test_a_local_web_ui_shows_its_model_and_that_nothing_leaves(page, fake):
    panel = _open_inspector_tab(page, "Prompt")
    page.wait_for_selector("text=Change image provider")
    page.select_option('select[aria-label="Image provider"]', "automatic1111")
    page.fill('input[aria-label="Web UI address"]', fake.url("a1111"))
    page.click('section[aria-label="Image provider settings"] button:has-text("Verify and save")')
    page.wait_for_selector("text=Model: sdxl_base.safetensors [31e35c80fc]")
    assert "NONE, STAYS ON THIS COMPUTER" in panel.inner_text()


def test_a_failed_generation_is_said_and_nothing_is_added(page, fake):
    fake.fail["pollinations"] = (500, b'{"error": "upstream exploded"}', "application/json")
    panel = _open_inspector_tab(page, "Media")
    page.wait_for_selector("text=Made by Free public generator")
    before = panel.inner_text()
    page.fill('textarea[aria-label="Image concept"]', "A calm desk at dawn")
    page.click('button:has-text("Generate")')
    page.wait_for_selector("text=had a problem of its own (HTTP 500)", timeout=15000)
    assert "Added to the library" not in panel.inner_text()
    assert ("local asset" in before) == ("local asset" in panel.inner_text())

    fake.fail.clear()
    page.click('button:has-text("Generate")')
    page.wait_for_selector("text=Added to the library.", timeout=15000)


def test_with_images_off_generate_is_disabled_and_says_where_to_change_it(page):
    import image_providers

    image_providers.save("off")
    panel = _open_inspector_tab(page, "Media")
    page.wait_for_selector("text=Image generation is off. Choose an image provider in the Prompt tab.")
    page.fill('textarea[aria-label="Image concept"]', "A calm desk at dawn")
    assert page.locator('button:has-text("Generate")').is_disabled()
    assert "Change it in the Prompt tab." in panel.inner_text()
