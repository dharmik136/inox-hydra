"""
The image provider setting (cycle 2, batch R7).

The creator chooses who makes their images in the Prompt tab, beside the AI
provider: the free public generator (the default), a cloud account of their
own (OpenAI, Google Imagen, Stability AI, Replicate, fal.ai, Together), or a
web UI on their own machine (AUTOMATIC1111 or Forge, ComfyUI), or Off. Each
is checked without making an image where the provider allows it, shows the
model, and says what leaves the machine. Keys are handled the way WRITE-04
fixed the AI key: sealed, in a header, masked, never returned, scrubbed.

Every provider answers from the fake on 127.0.0.1; no real service is called.
"""

import json
import os
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import qc2_r7_fake_images as fakes  # noqa: E402
from test_qc2_r7_images import _generate, _media_count, fake, studio  # noqa: E402,F401

GOOD = fakes.GOOD_KEY
PLANTED = "sk-notarealkey-r7-planted-abcdef0123456789"


@pytest.mark.parametrize("provider,model,prefix,key_header", [
    ("openai", "gpt-image-1", "openai", "Authorization"),
    ("openai", "dall-e-3", "openai", "Authorization"),
    ("gemini", "imagen-4.0-generate-001", "gemini", "x-goog-api-key"),
    ("stability", "stable-image-core", "stability", "Authorization"),
    ("stability", "sd3.5-large", "stability", "Authorization"),
    ("replicate", "black-forest-labs/flux-schnell", "replicate", "Authorization"),
    ("fal", "fal-ai/flux/schnell", "fal", "Authorization"),
    ("together", "black-forest-labs/FLUX.1-schnell", "together", "Authorization"),
])
def test_a_cloud_provider_is_checked_saved_and_used(studio, fake, provider, model, prefix, key_header):
    saved = studio.post("/api/image/provider", json={"provider": provider, "api_key": GOOD, "model": model})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    config = body["config"]
    assert config["provider"] == provider and config["model"] == model and config["source"] == "chosen"
    assert config["api_key_masked"] == "..." + GOOD[-4:]
    assert GOOD not in json.dumps(body)
    assert config["disclosure"]["leaves"] is True
    if provider == "fal":
        assert "not checked" in body["message"] and config["verified_at"] == ""
    else:
        assert f"Model: " in body["message"] and config["verified_at"]

    fake.requests.clear()
    progress = _generate(studio)
    assert progress["status"] == "completed", progress

    sent = [r for r in fake.requests]
    assert sent and all(r["prefix"] == prefix for r in sent)
    first = sent[0]
    assert GOOD in first["headers"].get(key_header, ""), "the key was not in the header"
    for request in sent:
        assert GOOD not in request["raw_path"], "the key travelled in a URL"
    blob = json.dumps(first["json"]) if first["json"] else first["body"].decode("latin-1")
    assert "calm desk at dawn" in blob, "the prompt did not reach the provider"
    if provider == "stability":
        assert b"negative_prompt" in first["body"]


def test_the_saved_key_is_sealed_and_never_returned(studio, fake):
    from database import get_db

    studio.post("/api/image/provider", json={"provider": "openai", "api_key": GOOD})
    conn = get_db()
    stored = conn.execute("SELECT value FROM settings WHERE key = 'ai_image_api_key'").fetchone()[0]
    conn.close()
    assert stored and GOOD not in stored, "the key is stored in plain text"
    listing = studio.get("/api/image/provider").json()
    assert GOOD not in json.dumps(listing)
    assert listing["config"]["has_key"] is True


def test_a_refused_key_is_scrubbed_from_the_answer_and_nothing_is_saved(studio, fake, capfd):
    studio.post("/api/image/provider", json={"provider": "pollinations"})
    refused = studio.post("/api/image/provider", json={"provider": "openai", "api_key": PLANTED})
    assert refused.status_code == 400
    assert "refused the key (HTTP 401)" in refused.json()["detail"]
    assert PLANTED not in refused.text and PLANTED[-8:] not in refused.text
    assert studio.get("/api/image/provider").json()["config"]["provider"] == "pollinations"
    out, err = capfd.readouterr()
    assert PLANTED not in out + err


def test_a_failed_generation_scrubs_a_key_the_provider_quotes(studio, fake):
    studio.post("/api/image/provider", json={"provider": "together", "api_key": GOOD})
    fake.fail["together"] = (400, json.dumps({"error": {"message": f"bad request for key {GOOD}"}}).encode(), "application/json")
    progress = _generate(studio)
    assert progress["status"] == "failed"
    assert GOOD not in json.dumps(progress) and "[redacted]" in progress["error_message"]


def test_an_unknown_model_is_named(studio, fake):
    refused = studio.post("/api/image/provider", json={"provider": "openai", "api_key": GOOD, "model": "gpt-image-9"})
    assert refused.status_code == 400 and "gpt-image-9" in refused.json()["detail"]


def test_a_blank_key_keeps_the_saved_one(studio, fake):
    studio.post("/api/image/provider", json={"provider": "openai", "api_key": GOOD})
    again = studio.post("/api/image/provider", json={"provider": "openai", "api_key": "", "model": "dall-e-3"})
    assert again.status_code == 200, again.text
    assert again.json()["config"]["model"] == "dall-e-3" and again.json()["config"]["has_key"]


def test_a_blank_key_for_another_provider_is_asked_for(studio, fake):
    refused = studio.post("/api/image/provider", json={"provider": "stability", "api_key": ""})
    assert refused.status_code == 400 and "Enter your Stability AI key" in refused.json()["detail"]


def test_with_nothing_chosen_the_free_generator_is_the_default(studio):
    listing = studio.get("/api/image/provider").json()
    config = listing["config"]
    assert config["provider"] == "pollinations" and config["source"] == "default" and config["ready"]
    assert "image.pollinations.ai" in config["disclosure"]["to"]
    ids = [p["id"] for p in listing["providers"]]
    assert ids == ["pollinations", "openai", "gemini", "stability", "replicate", "fal", "together",
                   "automatic1111", "comfyui", "off"]
    for option in listing["providers"]:
        assert option["disclosure"]["sends"] and option["disclosure"]["to"], option["id"]


def test_an_openai_ai_provider_makes_the_images_when_nothing_is_chosen(studio, fake, monkeypatch):
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(model_gateway.AIProviderConfig(provider="openai", api_key=GOOD, model="gpt-4o"))
    try:
        config = studio.get("/api/image/provider").json()["config"]
        assert config["provider"] == "openai" and config["source"] == "ai_provider"
        fake.requests.clear()
        assert _generate(studio)["status"] == "completed"
        assert fake.requests[0]["prefix"] == "openai"
        # And it can be chosen here with a blank key, using that key.
        chosen = studio.post("/api/image/provider", json={"provider": "openai", "api_key": ""})
        assert chosen.status_code == 200 and chosen.json()["config"]["key_from"] == "ai_provider"
    finally:
        model_gateway.save_ai_config(provider="local_deterministic")
    gone = studio.get("/api/image/provider").json()["config"]
    assert gone["ready"] is False and "AI provider's key" in gone["not_ready"]


def test_automatic1111_shows_its_models_and_renders(studio, fake):
    saved = studio.post("/api/image/provider", json={"provider": "automatic1111", "base_url": fake.url("a1111")})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert "sdxl_base.safetensors [31e35c80fc]" in body["message"]
    assert "dreamshaper_8.safetensors [879db523c3]" in body["models"]
    assert body["config"]["disclosure"]["leaves"] is False
    assert "this computer" in body["config"]["disclosure"]["to"]

    fake.requests.clear()
    assert _generate(studio)["status"] == "completed"
    txt2img = [r for r in fake.requests if r["path"] == "/sdapi/v1/txt2img"][0]
    assert txt2img["json"]["negative_prompt"]


def test_automatic1111_without_its_api_says_how_to_start_it(studio, fake):
    refused = studio.post("/api/image/provider", json={"provider": "automatic1111", "base_url": fake.url("a1111-noapi")})
    assert refused.status_code == 400 and "--api" in refused.json()["detail"]


def test_a_web_ui_that_is_not_running_is_said_so(studio):
    refused = studio.post("/api/image/provider", json={"provider": "comfyui", "base_url": "http://127.0.0.1:9"})
    assert refused.status_code == 400
    assert "Nothing answered at http://127.0.0.1:9" in refused.json()["detail"]


def test_comfyui_picks_a_checkpoint_and_renders(studio, fake):
    saved = studio.post("/api/image/provider", json={"provider": "comfyui", "base_url": fake.url("comfy")})
    assert saved.status_code == 200, saved.text
    assert saved.json()["config"]["model"] == "sd_xl_base_1.0.safetensors"
    fake.requests.clear()
    assert _generate(studio)["status"] == "completed"
    queued = [r for r in fake.requests if r["path"] == "/prompt"][0]["json"]["prompt"]
    assert queued["4"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"
    assert "calm desk at dawn" in queued["6"]["inputs"]["text"]


def test_a_web_ui_on_this_computer_works_with_egress_off(studio, fake, monkeypatch):
    """Nothing leaves the machine, so INOX_NO_EGRESS does not refuse it."""
    import egress

    studio.post("/api/image/provider", json={"provider": "automatic1111", "base_url": fake.url("a1111")})
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    egress.reset_for_tests()
    assert _generate(studio)["status"] == "completed"
    assert egress.stats_for("image")["performed"] == 0 and egress.stats_for("image")["refused"] == 0


def test_a_cloud_provider_is_not_checked_or_saved_with_egress_off(studio, fake, monkeypatch):
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    refused = studio.post("/api/image/provider", json={"provider": "openai", "api_key": GOOD})
    assert refused.status_code == 400 and "not saved" in refused.json()["detail"]
    assert fake.requests == []


@pytest.mark.parametrize("url,accepted,where", [
    ("http://192.168.1.20:7860", True, "another computer on your network"),
    ("http://gpu-box:7860", True, "another computer on your network"),
    ("https://sd.example.com", True, "a server on the internet"),
    ("http://sd.example.com", False, "needs https"),
    ("http://user:pw@127.0.0.1:7860", False, "without a name, password"),
    ("ftp://127.0.0.1", False, "web address"),
])
def test_a_web_ui_address_is_checked_and_described(url, accepted, where):
    import image_providers

    if accepted:
        assert image_providers._check_url("automatic1111", url) == url
        assert where in image_providers.disclosure("automatic1111", url)["to"]
    else:
        with pytest.raises(image_providers.ImageProviderError) as refused:
            image_providers._check_url("automatic1111", url)
        assert where in str(refused.value)


def test_a_model_name_cannot_walk_the_request_path(studio):
    refused = studio.post("/api/image/provider", json={"provider": "replicate", "api_key": GOOD, "model": "../../account"})
    assert refused.status_code == 400 and "model name" in refused.json()["detail"]


def test_replicate_downloads_only_from_https_or_its_own_address(studio, fake):
    import image_providers

    config = image_providers.ImageProviderConfig("replicate", "", GOOD)
    with pytest.raises(image_providers.ImageProviderError) as refused:
        image_providers._download("http://169.254.169.254/latest", "https://api.replicate.com/v1", config)
    assert "does not follow" in str(refused.value)


def test_replicate_sends_no_key_to_its_file_host(studio, fake):
    studio.post("/api/image/provider", json={"provider": "replicate", "api_key": GOOD})
    fake.requests.clear()
    assert _generate(studio)["status"] == "completed"
    download = [r for r in fake.requests if r["path"] == "/files/out.jpg"][0]
    assert "Authorization" not in download["headers"]


def test_the_settings_are_cleared_with_the_ai_setup_on_reset():
    """reset --keep-data clears every ai_ setting; the image ones share the prefix."""
    import support

    assert support.RESET_SETTING_PREFIX == "ai_"
    import image_providers

    assert all(key.startswith("ai_image_") for key in image_providers._ALL_KEYS)
