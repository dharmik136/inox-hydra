"""
AI Image Studio Test Suite
==========================
Tests generative prompt synthesis, async task orchestration,
progressive 1% to 100% progress tracking, and local image persistence.
"""

import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from database import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_synthesize_prompt_endpoint():
    """Verifies that Agno prompt synthesis constructs a complete prompt blueprint."""
    payload = {
        "concept": "Event-driven distributed Kafka clusters",
        "aspect_ratio": "1:1",
        "visual_style": "blueprint",
        "color_palette": "navy_cyan",
        "lighting": "studio"
    }
    resp = client.post("/api/image/synthesize-prompt", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    synth = data["synthesized"]
    assert "Kafka" in synth["master_prompt"]
    assert synth["aspect_ratio"] == "1:1"
    assert synth["width"] == 1080
    assert synth["height"] == 1080
    assert len(synth["negative_prompt"]) > 10


def test_image_generation_task_lifecycle():
    """Tests the end-to-end async generation workflow with progress tracking from 1% to 100%."""
    payload = {
        "concept": "Zero-downtime database failover diagram",
        "aspect_ratio": "1:1",
        "visual_style": "isometric_3d",
        "color_palette": "obsidian_indigo",
        "lighting": "neon_cyber"
    }
    # 1. Start generation task
    start_resp = client.post("/api/image/generate", json=payload)
    assert start_resp.status_code == 200
    task_data = start_resp.json()
    assert task_data["status"] == "started"
    task_id = task_data["task_id"]
    assert task_id.startswith("img_task_")

    # 2. Check initial progress (>=1%)
    prog_resp = client.get(f"/api/image/progress/{task_id}")
    assert prog_resp.status_code == 200
    prog_data = prog_resp.json()
    assert prog_data["progress_percent"] >= 1
    assert "status_message" in prog_data

    # 3. Poll until completion (max 10 seconds)
    max_wait = 10
    start_time = time.time()
    completed = False

    while time.time() - start_time < max_wait:
        p_resp = client.get(f"/api/image/progress/{task_id}")
        p_data = p_resp.json()
        if p_data["progress_percent"] == 100 or p_data["status"] in ("completed", "failed"):
            completed = True
            break
        time.sleep(0.3)

    assert completed, "Task did not reach completion within timeout"
    final_data = client.get(f"/api/image/progress/{task_id}").json()
    assert final_data["progress_percent"] == 100
    assert final_data["status"] == "completed"
    assert final_data["result_url"] is not None
    assert final_data["result_url"].startswith("/assets/generated/")


def test_nonexistent_task_progress():
    """Verifies that polling a non-existent task returns proper status."""
    resp = client.get("/api/image/progress/img_task_nonexistent_999")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_found"


def test_watermark_removal_crop_all_ratios():
    """
    Verifies that remove_watermark_crop accurately shears off the oversampled bottom buffer
    and outputs exact target dimensions for 1:1, 4:5, and 16:9 aspect ratios.
    """
    import io
    from PIL import Image, ImageDraw
    from quote_renderer import remove_watermark_crop

    # Test cases: (name, target_w, target_h, oversample_w, oversample_h, expected_cut)
    test_cases = [
        ("1:1 Square", 1080, 1080, 768, 864, 96),
        ("4:5 Portrait", 1080, 1350, 768, 1080, 120),
        ("16:9 Landscape", 1920, 1080, 1080, 688, 81),
    ]

    for name, tw, th, ow, oh, min_cut in test_cases:
        # Create an oversampled image with a bright simulated watermark stamp in the bottom 40px
        raw_img = Image.new("RGB", (ow, oh), color=(20, 30, 45))
        draw = ImageDraw.Draw(raw_img)
        # Draw fake watermark in bottom right
        draw.rectangle([ow - 150, oh - 35, ow - 10, oh - 5], fill=(255, 0, 0))

        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        clean_bytes, clean_img = remove_watermark_crop(raw_bytes, tw, th)

        # 1. Output dimensions must match exact target
        assert clean_img.size == (tw, th), f"Failed dimensions for {name}: expected {(tw, th)}, got {clean_img.size}"

        # 2. The red simulated watermark should have been in the bottom buffer that got sliced off
        # Check bottom right pixel in cleaned image
        px = clean_img.getpixel((tw - 20, th - 20))
        # The pixel must NOT be the red watermark color (255, 0, 0)
        assert px != (255, 0, 0), f"Watermark was not eliminated in {name}!"


def test_quote_synthesis_and_bust_prevention():
    """
    Verifies that a philosophical quote requested in a setting (e.g. Socrates in a quiet room)
    formulates an architectural scene prompt and suppresses bust/statue hallucinations.
    """
    payload = {
        "concept": "i need quote based on socrates in a quiet dark and white room with a light flowing from the corner",
        "aspect_ratio": "1:1",
        "visual_style": "minimalist_sketch",
        "color_palette": "obsidian_monochrome",
        "lighting": "cinematic"
    }
    resp = client.post("/api/image/synthesize-prompt", json=payload)
    assert resp.status_code == 200
    data = resp.json()["synthesized"]

    # 1. Master prompt should focus on the room / sunlight environment
    assert "room" in data["master_prompt"].lower() or "architectural" in data["master_prompt"].lower()

    # 2. Negative prompt must suppress marble busts and statues
    assert "marble bust" in data["negative_prompt"].lower()
    assert "statue" in data["negative_prompt"].lower()

    # 3. Technical parameters must capture extracted quote
    params = data.get("technical_parameters", {})
    assert params.get("quote_text") == "The only true wisdom is in knowing you know nothing."
    assert params.get("quote_author") == "Socrates"


def test_render_typographic_quote_compositor():
    """
    Verifies that render_typographic_quote composites a high-fidelity quote card onto a base image.
    """
    from PIL import Image
    from quote_renderer import render_typographic_quote

    base = Image.new("RGB", (1080, 1080), color=(15, 23, 42))
    quoted = render_typographic_quote(base, "The only true wisdom is in knowing you know nothing.", "Socrates")

    assert quoted.size == (1080, 1080)
    # The center card should have text and glass background differing from (15, 23, 42)
    center_px = quoted.getpixel((540, 540))
    assert center_px != (15, 23, 42), "Quote overlay was not rendered onto image"


def test_creator_profile_endpoints():
    """
    Verifies retrieval and persistence of creator onboarding profile and personal watermark defaults.
    """
    # 1. GET initial profile
    get_res = client.get("/api/settings/profile")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["status"] == "success"
    assert "profile" in data
    assert "brand_watermark_text" in data["profile"]
    assert "linkedin_connected" in data

    # 2. Update profile with custom branding
    new_profile = {
        "name": "Dharmik Shingala",
        "headline": "Full-Stack AI Architect",
        "company": "Enterprise Labs",
        "brand_watermark_text": "@dharmik136",
        "brand_watermark_position": "bottom_right",
        "brand_watermark_style": "glass_pill",
        "brand_watermark_enabled": True,
        "eliminate_provider_watermark_default": True,
        "default_aspect_ratio": "1:1",
        "default_visual_style": "photorealistic"
    }
    post_res = client.post("/api/settings/profile", json=new_profile)
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "success"

    # 3. Verify changes persisted in GET
    verify_res = client.get("/api/settings/profile")
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["profile"]["headline"] == "Full-Stack AI Architect"
    assert v_data["profile"]["brand_watermark_text"] == "@dharmik136"
    assert v_data["profile"]["brand_watermark_position"] == "bottom_right"


def test_personal_brand_watermark_compositor():
    """
    Verifies that apply_personal_brand_watermark correctly applies custom badges
    across 4 corner positions and all styling presets.
    """
    from PIL import Image
    from quote_renderer import apply_personal_brand_watermark

    positions = ["bottom_right", "bottom_left", "top_right", "top_left"]
    styles = ["glass_pill", "minimal_text", "accent_badge"]

    for pos in positions:
        for sty in styles:
            base = Image.new("RGB", (1080, 1080), color=(15, 23, 42))
            stamped = apply_personal_brand_watermark(base, brand_text="@dharmik136", position=pos, style=sty)
            assert stamped.size == (1080, 1080)
            assert isinstance(stamped, Image.Image)


def test_image_generation_with_watermark_switches():
    """
    Verifies that the generation task accepts eliminate_provider_watermark and apply_personal_watermark.
    """
    payload = {
        "concept": "Microservices event storming architecture canvas",
        "aspect_ratio": "1:1",
        "visual_style": "photorealistic",
        "eliminate_provider_watermark": False,
        "apply_personal_watermark": True,
        "personal_watermark_text": "@dharmik136",
        "personal_watermark_position": "bottom_right",
        "personal_watermark_style": "glass_pill"
    }
    start_resp = client.post("/api/image/generate", json=payload)
    assert start_resp.status_code == 200
    task_id = start_resp.json()["task_id"]

    # Poll until done
    max_wait = 10
    start_time = time.time()
    while time.time() - start_time < max_wait:
        p_data = client.get(f"/api/image/progress/{task_id}").json()
        if p_data["progress_percent"] == 100 or p_data["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)

    final_data = client.get(f"/api/image/progress/{task_id}").json()
    assert final_data["status"] == "completed"
    assert final_data["result_url"] is not None

