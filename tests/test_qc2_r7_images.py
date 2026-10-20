"""
A failed or refused image is reported as failed, and nothing is saved. [BE-06]

Offline, under INOX_NO_EGRESS=1, or on any provider error, the worker caught
the failure, drew a grey grid labelled AI STUDIO GENERATION, filed it in the
media library and reported "Image rendering complete and verified!". The
creator got a placeholder as a generated image, which could end up in a post.

Now the chosen provider is the only one asked. Its failure, or the egress
guard's refusal, ends the task as failed with the reason, and no file and no
media_assets row is written. A success says which provider made the image and
claims no verification it did not do.

Nothing here reaches the network: every provider answers from a fake on
127.0.0.1 (tests/qc2_r7_fake_images.py), and a socket guard refuses any other
address before a connection is made.
"""

import io
import os
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

import qc2_r7_fake_images as fakes  # noqa: E402

IMAGE_KEYS = ("ai_image_provider", "ai_image_api_key", "ai_image_model", "ai_image_base_url",
              "ai_image_verified_at", "ai_image_check", "ai_image_key_from")


@pytest.fixture(scope="module")
def fake():
    server = fakes.FakeImageServer().start()
    yield server
    server.stop()


def _provider_modules():
    return [m for n, m in list(sys.modules.items()) if n.rsplit(".", 1)[-1] == "image_providers" and m]


@pytest.fixture
def studio(fake, monkeypatch):
    """The app, offline, with every cloud endpoint at the fake and no image setup saved."""
    fakes.install_socket_guard(monkeypatch)
    for name in ("INOX_NO_EGRESS", "INOX_ALLOW_IMAGE_EGRESS", "OPENAI_API_KEY", "GEMINI_API_KEY",
                 "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    from app import app
    import egress
    from database import get_db
    from agno_agentos import model_gateway

    for module in _provider_modules():
        monkeypatch.setattr(module, "ENDPOINTS", {k: fake.url(k) for k in module.ENDPOINTS})
    model_gateway.save_ai_config(provider="local_deterministic")

    def clear():
        conn = get_db()
        with conn:
            conn.execute(f"DELETE FROM settings WHERE key IN ({','.join('?' * len(IMAGE_KEYS))})", IMAGE_KEYS)
        conn.close()

    clear()
    egress.reset_for_tests()
    fake.requests.clear()
    fake.fail.clear()
    yield TestClient(app)
    clear()
    fake.fail.clear()


def _media_count():
    from database import get_db

    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0]
    finally:
        conn.close()


def _generated_files():
    import paths

    return set(os.listdir(paths.get_generated_dir()))


def _generate(client, concept="Our Q3 pricing migration, a calm desk at dawn", **extra):
    started = client.post("/api/image/generate", json={"concept": concept, "render_quote_overlay": False, **extra})
    assert started.status_code == 200, started.text
    task_id = started.json()["task_id"]
    deadline = time.time() + 30
    while time.time() < deadline:
        progress = client.get(f"/api/image/progress/{task_id}").json()
        if progress["status"] in ("completed", "failed"):
            return progress
        time.sleep(0.05)
    raise AssertionError(f"the task did not finish: {progress}")


def test_a_refused_generation_fails_and_saves_nothing(studio, fake, monkeypatch):
    """The auditor's repro: INOX_NO_EGRESS=1 and the free public generator."""
    import egress

    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    before_rows, before_files = _media_count(), _generated_files()

    progress = _generate(studio)

    assert progress["status"] == "failed", progress
    assert "INOX_NO_EGRESS" in progress["error_message"]
    assert "Nothing was sent" in progress["error_message"]
    assert "verified" not in progress["status_message"].lower()
    assert progress["result_url"] is None
    assert _media_count() == before_rows, "a placeholder was filed in the media library"
    assert _generated_files() == before_files, "a placeholder file was written"
    image = egress.stats_for("image")
    assert image["refused"] == 1 and image["performed"] == 0
    assert fake.requests == []


@pytest.mark.parametrize("status,body,ctype,expected", [
    (500, b'{"error": "upstream exploded"}', "application/json", "had a problem of its own (HTTP 500)"),
    (200, b"<html>rate limited</html>", "text/html", "returned something that is not an image"),
    (429, b"{}", "application/json", "(HTTP 429)"),
])
def test_a_provider_failure_fails_and_saves_nothing(studio, fake, status, body, ctype, expected):
    fake.fail["pollinations"] = (status, body, ctype)
    before_rows, before_files = _media_count(), _generated_files()

    progress = _generate(studio)

    assert progress["status"] == "failed", progress
    assert expected in progress["error_message"]
    assert progress["status_message"].startswith("Generation failed: ")
    assert _media_count() == before_rows
    assert _generated_files() == before_files


def test_an_unreachable_provider_fails_with_where_it_tried(studio, fake, monkeypatch):
    for module in _provider_modules():
        monkeypatch.setitem(module.ENDPOINTS, "pollinations", "https://image.pollinations.ai")
    before_rows = _media_count()

    progress = _generate(studio)

    assert progress["status"] == "failed"
    assert "Could not reach image.pollinations.ai" in progress["error_message"]
    assert _media_count() == before_rows


def test_a_success_says_who_made_it_and_claims_no_verification(studio, fake):
    from PIL import Image
    import paths

    before_rows = _media_count()
    progress = _generate(studio)

    assert progress["status"] == "completed", progress
    assert "verified" not in progress["status_message"].lower()
    assert "Free public generator" in progress["status_message"]
    assert _media_count() == before_rows + 1
    path = os.path.join(paths.get_generated_dir(), progress["result_url"].rsplit("/", 1)[-1])
    with Image.open(path) as saved:
        assert saved.format == "JPEG" and saved.size == (1080, 1080)
    assert [r["prefix"] for r in fake.requests] == ["pollinations"]


def test_generate_is_refused_at_once_when_images_are_off(studio):
    saved = studio.post("/api/image/provider", json={"provider": "off"})
    assert saved.status_code == 200, saved.text
    before_rows = _media_count()

    refused = studio.post("/api/image/generate", json={"concept": "a calm desk at dawn"})

    assert refused.status_code == 409
    assert "Image generation is off" in refused.json()["detail"]
    assert _media_count() == before_rows


def test_a_quote_that_cannot_be_drawn_is_said_on_the_finished_image(studio, fake, monkeypatch):
    import quote_renderer

    monkeypatch.setattr(quote_renderer, "shaping_available", lambda: False)
    progress = _generate(studio, concept='A calm desk "पहले सरल संस्करण भेजें"', render_quote_overlay=True)

    assert progress["status"] == "completed", progress
    assert progress["notice"] and "The quote was not drawn" in progress["notice"]
    assert "The quote was not drawn" in progress["status_message"]


def test_the_placeholder_painter_is_gone():
    import image_studio

    source = io.open(image_studio.__file__, encoding="utf-8").read()
    assert not hasattr(image_studio.ImageStudioManager, "_create_local_canvas_image")
    assert "AI STUDIO GENERATION\"" not in source
    assert "Image rendering complete and verified" not in source
