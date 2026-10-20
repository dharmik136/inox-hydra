"""
R7 review send-back and note (cycle 2).

1. [BE-06] A web UI on this computer is exempt from the egress guard, because
   nothing leaves the machine. requests follows redirects by default, so a
   loopback address that answered 307 had the prompt re-sent to whatever host
   its Location named, past the guard, under INOX_NO_EGRESS, while the Prompt
   tab said "STAYS ON THIS COMPUTER". No image provider request follows a
   redirect to another address now, on any path: generation, checks, polls
   and downloads. A redirect within the same scheme, host and port is
   followed, since it goes nowhere new.

2. Existing OpenAI and Gemini users who never chose an image provider were
   moved from dall-e-3 to gpt-image-1 and from imagen-3.0-generate-002 to
   imagen-4.0-generate-001, which are priced differently, and gpt-image-1
   needs OpenAI organisation verification. They keep the model they had until
   they choose another; a new setup may start on the newer model, with its
   requirement stated beside it.

Every request answers from the fake on 127.0.0.1 behind the socket guard.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import qc2_r7_fake_images as fakes  # noqa: E402
from test_qc2_r7_images import _generate, _media_count, fake, studio  # noqa: E402,F401

GOOD = fakes.GOOD_KEY
ELSEWHERE = "http://192.168.77.77:7860/sdapi/v1/txt2img"


# -- 1. redirects -------------------------------------------------------------

def test_a_loopback_web_ui_that_redirects_elsewhere_sends_nothing_there(studio, fake, monkeypatch):
    """The reviewer's repro, under INOX_NO_EGRESS."""
    saved = studio.post("/api/image/provider", json={"provider": "automatic1111", "base_url": fake.url("a1111")})
    assert saved.status_code == 200, saved.text
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    fake.redirect["a1111"] = (307, ELSEWHERE)
    fakes.REFUSED.clear()
    before = _media_count()

    progress = _generate(studio)

    assert fakes.REFUSED == [], f"the prompt was re-sent past the guard to {fakes.REFUSED}"
    assert progress["status"] == "failed"
    assert "redirect" in progress["error_message"] and "192.168.77.77" in progress["error_message"]
    assert "Nothing answered" not in progress["error_message"]
    assert _media_count() == before


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_check_is_not_redirected_elsewhere_either(studio, fake, status):
    fake.redirect["comfy"] = (status, "http://10.9.9.9:8188/object_info/CheckpointLoaderSimple")
    fakes.REFUSED.clear()
    refused = studio.post("/api/image/provider", json={"provider": "comfyui", "base_url": fake.url("comfy")})
    assert refused.status_code == 400
    assert "redirect" in refused.json()["detail"]
    assert fakes.REFUSED == []


@pytest.mark.parametrize("provider,prefix", [
    ("openai", "openai"), ("gemini", "gemini"), ("stability", "stability"),
    ("together", "together"), ("fal", "fal"), ("replicate", "replicate"),
])
def test_a_cloud_provider_that_redirects_elsewhere_is_not_followed(studio, fake, provider, prefix):
    """The key travels in a header; a redirect to another host must not carry it there."""
    saved = studio.post("/api/image/provider", json={"provider": provider, "api_key": GOOD})
    assert saved.status_code == 200, saved.text
    fake.redirect[prefix] = (307, "https://collector.invalid/steal")
    fakes.REFUSED.clear()

    progress = _generate(studio)

    assert progress["status"] == "failed"
    assert "redirect" in progress["error_message"]
    assert fakes.REFUSED == [], fakes.REFUSED


def test_the_free_generator_that_redirects_elsewhere_is_not_followed(studio, fake):
    fake.redirect["pollinations"] = (302, "https://collector.invalid/image.jpg")
    fakes.REFUSED.clear()
    progress = _generate(studio)
    assert progress["status"] == "failed" and "redirect" in progress["error_message"]
    assert fakes.REFUSED == []


def test_a_redirect_within_the_same_web_ui_is_followed(studio, fake):
    """Same scheme, host and port: nothing goes anywhere new."""
    fake.redirect["a1111-moved"] = (307, fake.url("a1111") + "{path}")
    saved = studio.post("/api/image/provider", json={"provider": "automatic1111", "base_url": fake.url("a1111-moved")})
    # The check is redirected to the real web UI on the same server...
    assert saved.status_code == 200, saved.text
    assert "sdxl_base.safetensors" in saved.json()["message"]
    progress = _generate(studio)
    # ...and so is the render, POST and body included (307 keeps both).
    assert progress["status"] == "completed", progress
    txt2img = [r for r in fake.requests if r["prefix"] == "a1111" and r["path"] == "/sdapi/v1/txt2img"]
    assert txt2img and txt2img[-1]["method"] == "POST" and txt2img[-1]["json"]["prompt"]


def test_every_provider_request_refuses_automatic_redirects():
    """Structural: the one place requests is called passes allow_redirects=False."""
    import io
    import re

    import image_providers

    source = io.open(image_providers.__file__, encoding="utf-8").read()
    calls = re.findall(r"requests\.(?:get|post|request)\((.*)", source)
    assert calls, "no request call found"
    for call in calls:
        assert "allow_redirects=False" in call, call


def test_offline_reads_as_a_sentence_not_a_library_repr(studio, fake, monkeypatch):
    """Reviewer note: 'Could not reach image.pollinations.ai: NameResolutionError("HTTPSConnection(...'."""
    for module in [m for n, m in list(sys.modules.items()) if n.rsplit(".", 1)[-1] == "image_providers" and m]:
        monkeypatch.setitem(module.ENDPOINTS, "pollinations", "https://image.pollinations.ai")
    progress = _generate(studio)
    assert progress["status"] == "failed"
    assert progress["error_message"] == (
        "Could not reach image.pollinations.ai: its name could not be looked up. Check that this computer is online."
    )


# -- 2. existing users keep their model ---------------------------------------

@pytest.mark.parametrize("provider,old_model", [("openai", "dall-e-3"), ("gemini", "imagen-3.0-generate-002")])
def test_an_existing_ai_provider_user_keeps_the_model_they_had(studio, fake, provider, old_model):
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(model_gateway.AIProviderConfig(provider=provider, api_key=GOOD))
    try:
        config = studio.get("/api/image/provider").json()["config"]
        assert config["source"] == "ai_provider" and config["model"] == old_model

        fake.requests.clear()
        assert _generate(studio)["status"] == "completed"
        sent = fake.requests[0]
        if provider == "openai":
            assert sent["json"]["model"] == "dall-e-3"
        else:
            assert old_model in sent["path"]

        # Choosing the same company here with the model field left empty
        # keeps it too; only a model they pick changes it.
        kept = studio.post("/api/image/provider", json={"provider": provider, "api_key": ""})
        assert kept.status_code == 200, kept.text
        assert kept.json()["config"]["model"] == old_model
    finally:
        model_gateway.save_ai_config(provider="local_deterministic")


def test_a_new_setup_starts_on_the_newer_model_with_its_requirement_stated(studio):
    listing = studio.get("/api/image/provider").json()
    openai = next(p for p in listing["providers"] if p["id"] == "openai")
    assert openai["default_model"] == "gpt-image-1"
    assert "organisation" in openai["model_notes"]["gpt-image-1"]
    assert openai["model_notes"]["dall-e-3"]
    gemini = next(p for p in listing["providers"] if p["id"] == "gemini")
    assert gemini["model_notes"]["imagen-4.0-generate-001"] and gemini["model_notes"]["imagen-3.0-generate-002"]


def test_the_prompt_tab_shows_the_note_beside_the_model():
    path = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "ImageProviderSettings.tsx")
    source = open(path, encoding="utf-8").read()
    assert "model_notes" in source
