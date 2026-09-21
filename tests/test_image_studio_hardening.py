"""
AI Image Studio Module Production Hardening Test Suite.
=======================================================
Validates:
1. Default concept fallback when given empty or whitespace concept.
2. Length truncation of oversized concepts in start_task.
3. Fast API-boundary 422 validation on empty or whitespace concepts.
4. Fast API-boundary 422 validation on oversized concepts (>2000 chars).
5. ZeroDivisionError prevention in _call_pollinations with height=0 or width=0.
6. ZeroDivisionError prevention in remove_watermark_crop with zero dimensions.
7. Graceful handling of None title and style in _create_local_canvas_image.
8. Safe boundary clamping for small and extreme dimensions in local canvas.
9. Bounded in-memory task dictionary pruning to prevent memory leaks.
10. Strict zero em-dash compliance across all modified files.
"""

import os
import sys
import io
import time
import pytest
from PIL import Image
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from database import init_db
from image_studio import (
    image_studio_manager,
    MAX_CONCEPT_LENGTH,
    MIN_DIMENSION,
    MAX_DIMENSION,
    MAX_STORED_TASKS,
)
from quote_renderer import remove_watermark_crop

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_empty_concept_start_task_gets_default():
    """Verifies that empty, whitespace, or None concept receives a safe fallback."""
    task_id1 = image_studio_manager.start_task({"concept": "   "})
    task1 = image_studio_manager.get_progress(task_id1)
    assert task1["status"] in ("pending", "processing", "completed")

    task_id2 = image_studio_manager.start_task({"concept": None})
    task2 = image_studio_manager.get_progress(task_id2)
    assert task2["status"] in ("pending", "processing", "completed")


def test_concept_length_truncated_in_start_task():
    """Verifies that concepts exceeding MAX_CONCEPT_LENGTH are clamped."""
    oversized = "K" * 4000
    task_id = image_studio_manager.start_task({"concept": oversized})
    with image_studio_manager._lock:
        record = image_studio_manager._tasks.get(task_id)
        assert record is not None
        assert len(record["concept"]) <= MAX_CONCEPT_LENGTH


def test_api_empty_concept_rejected_422():
    """Verifies that POST /api/image/generate rejects empty or whitespace concept with 422."""
    resp = client.post("/api/image/generate", json={"concept": "   "})
    assert resp.status_code == 422

    resp2 = client.post("/api/image/generate", json={"concept": ""})
    assert resp2.status_code == 422


def test_api_oversized_concept_rejected_422():
    """Verifies that POST /api/image/generate rejects concepts over 2000 chars with 422."""
    resp = client.post("/api/image/generate", json={"concept": "Z" * 2001})
    assert resp.status_code == 422


def test_pollinations_zero_dimensions_safe():
    """Verifies that _call_pollinations guards against zero or negative dimensions."""
    # height=0 must not trigger ZeroDivisionError
    res = image_studio_manager._call_pollinations("Prompt test", width=1080, height=0)
    # The call should handle clamped dimensions safely (network call may return None or bytes)
    assert res is None or isinstance(res, bytes)

    # Negative dimensions must not crash
    res_neg = image_studio_manager._call_pollinations("Prompt test", width=-100, height=-50)
    assert res_neg is None or isinstance(res_neg, bytes)


def test_remove_watermark_crop_zero_dimensions_safe():
    """Verifies that remove_watermark_crop does not crash on zero target dimensions."""
    # Generate a dummy test image
    img = Image.new("RGB", (200, 200), color=(50, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    # Passing 0 as height must clamp safely instead of raising ZeroDivisionError
    clean_bytes, pil_img = remove_watermark_crop(raw_bytes, target_width=0, target_height=0)
    assert isinstance(clean_bytes, bytes)
    assert pil_img.size[0] >= MIN_DIMENSION
    assert pil_img.size[1] >= MIN_DIMENSION


def test_local_canvas_none_title_and_style_safe():
    """Verifies that _create_local_canvas_image handles None title and style without TypeError."""
    img_bytes = image_studio_manager._create_local_canvas_image(1080, 1080, None, None)
    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 500

    # Verify generated image can be opened by PIL
    pil_img = Image.open(io.BytesIO(img_bytes))
    assert pil_img.size == (1080, 1080)


def test_local_canvas_small_and_extreme_dimensions_clamped():
    """Verifies that _create_local_canvas_image clamps dimensions to [MIN_DIMENSION, MAX_DIMENSION]."""
    # Extremely small dimensions (e.g. 5x5) must be clamped to MIN_DIMENSION (64)
    small_bytes = image_studio_manager._create_local_canvas_image(5, 5, "Small", "Blueprint")
    pil_small = Image.open(io.BytesIO(small_bytes))
    assert pil_small.size[0] == MIN_DIMENSION
    assert pil_small.size[1] == MIN_DIMENSION

    # Extremely large dimensions must be clamped to MAX_DIMENSION (4096)
    large_bytes = image_studio_manager._create_local_canvas_image(99999, 99999, "Large", "Blueprint")
    pil_large = Image.open(io.BytesIO(large_bytes))
    assert pil_large.size[0] == MAX_DIMENSION
    assert pil_large.size[1] == MAX_DIMENSION


def test_task_memory_bounded_pruning():
    """Verifies that in-memory tasks dict prunes old records when reaching MAX_STORED_TASKS."""
    # Pre-populate dummy completed tasks in manager
    with image_studio_manager._lock:
        for i in range(MAX_STORED_TASKS + 5):
            tid = f"dummy_test_task_{i}"
            image_studio_manager._tasks[tid] = {
                "task_id": tid,
                "status": "completed",
                "created_at": time.time() - (1000 - i),
                "options": {}
            }

    # Start a new task, which should trigger memory pruning
    new_id = image_studio_manager.start_task({"concept": "Pruning Test Concept"})
    with image_studio_manager._lock:
        total_tasks = len(image_studio_manager._tasks)
        assert total_tasks <= MAX_STORED_TASKS + 1


def test_zero_em_dash_compliance():
    """Audits modified files for zero occurrences of the em-dash character."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    targets = [
        os.path.join(base_dir, "studio", "backend", "image_studio.py"),
        os.path.join(base_dir, "studio", "backend", "quote_renderer.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "tests", "test_image_studio_hardening.py"),
    ]

    for path in targets:
        assert os.path.exists(path), f"Target file does not exist: {path}"
        text = open(path, "r", encoding="utf-8").read()
        assert "\u2014" not in text, f"Illegal em-dash (\\u2014) found in: {path}"
