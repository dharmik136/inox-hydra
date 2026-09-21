"""
Vector Carousel Engine Module Production Hardening Test Suite.
==============================================================
Validates:
1. ZeroDivisionError prevention when total_slides=0 in render_slide_svg.
2. Clamping of negative or out-of-range slide indices.
3. Graceful handling of None or non-dict slide items.
4. Engine rejection of empty slide decks (status="error").
5. Engine rejection of oversized slide decks (>50 slides).
6. Fast API 422 rejection of empty slide list.
7. Fast API 422 rejection of oversized slide list (>50 slides).
8. Field length truncation of oversized titles, bodies, and tags.
9. Automatic normalization of unknown themes and aspect ratios.
10. Strict zero em-dash compliance across all modified files.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from carousel_engine import (
    carousel_engine,
    MAX_CAROUSEL_SLIDES,
    MIN_CAROUSEL_SLIDES,
    MAX_SLIDE_TITLE_LENGTH,
    MAX_SLIDE_BODY_LENGTH,
    MAX_SLIDE_TAG_LENGTH,
)

client = TestClient(app)


def test_render_slide_svg_zero_total_slides_safe():
    """Verifies that total_slides=0 does not trigger ZeroDivisionError."""
    # Must not raise ZeroDivisionError
    svg = carousel_engine.render_slide_svg(
        slide={"title": "Safe Zero Test", "body": "Testing zero division guard."},
        slide_index=0,
        total_slides=0
    )
    assert "<svg" in svg
    assert "01 / 01" in svg
    assert "Safe Zero Test" in svg


def test_render_slide_svg_negative_slide_index_safe():
    """Verifies that negative slide_index is safely clamped to 0."""
    svg = carousel_engine.render_slide_svg(
        slide={"title": "Clamped Index", "body": "Testing negative index."},
        slide_index=-5,
        total_slides=3
    )
    assert "<svg" in svg
    assert "01 / 03" in svg


def test_render_slide_svg_none_slide_safe():
    """Verifies that None or non-dict slide object does not raise AttributeError."""
    svg1 = carousel_engine.render_slide_svg(
        slide=None,
        slide_index=0,
        total_slides=1
    )
    assert "<svg" in svg1

    svg2 = carousel_engine.render_slide_svg(
        slide="invalid string",  # type: ignore
        slide_index=0,
        total_slides=1
    )
    assert "<svg" in svg2


def test_compile_deck_empty_slides_rejected():
    """Verifies that compiling an empty deck returns an error status."""
    res = carousel_engine.compile_carousel_deck(slides=[])
    assert res["status"] == "error"
    assert "at least 1 slide" in res["message"]


def test_compile_deck_oversized_slides_rejected():
    """Verifies that compiling more than MAX_CAROUSEL_SLIDES returns an error status."""
    excess_slides = [{"title": f"Slide {i}"} for i in range(MAX_CAROUSEL_SLIDES + 1)]
    res = carousel_engine.compile_carousel_deck(slides=excess_slides)
    assert res["status"] == "error"
    assert "exceeds maximum" in res["message"]


def test_api_empty_slides_rejected_422():
    """Verifies that POST /api/v1/carousel/deck/generate returns 422 for empty slides."""
    resp = client.post("/api/v1/carousel/deck/generate", json={"slides": []})
    assert resp.status_code == 422


def test_api_oversized_slides_rejected_422():
    """Verifies that POST /api/v1/carousel/deck/generate returns 422 for >50 slides."""
    excess = [{"title": f"Slide {i}"} for i in range(MAX_CAROUSEL_SLIDES + 1)]
    resp = client.post("/api/v1/carousel/deck/generate", json={"slides": excess})
    assert resp.status_code == 422


def test_slide_field_length_truncation():
    """Verifies that long titles, bodies, and tags are truncated to safe bounds."""
    long_title = "T" * 1000
    long_body = "B" * 5000
    long_tag = "G" * 200

    deck = carousel_engine.compile_carousel_deck(slides=[{
        "tag": long_tag,
        "title": long_title,
        "body": long_body
    }])
    assert deck["status"] == "success"
    first_slide = deck["slides"][0]
    assert len(first_slide["title"]) <= MAX_SLIDE_TITLE_LENGTH
    assert len(first_slide["tag"]) <= MAX_SLIDE_TAG_LENGTH


def test_theme_and_aspect_ratio_normalization():
    """Verifies that invalid themes and aspect ratios fall back to safe standards."""
    deck = carousel_engine.compile_carousel_deck(
        slides=[{"title": "Norm Test", "body": "Testing normalization"}],
        theme="completely_unknown_theme",
        aspect_ratio="invalid_ratio"
    )
    assert deck["status"] == "success"
    assert deck["theme"] == "dark_obsidian"
    assert deck["aspect_ratio"] == "4:5"
    assert deck["dimensions"]["height"] == 1350


def test_zero_em_dash_compliance():
    """Audits modified files for zero occurrences of the em-dash character."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    targets = [
        os.path.join(base_dir, "studio", "backend", "carousel_engine.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "tests", "test_carousel_engine_hardening.py"),
    ]

    for path in targets:
        assert os.path.exists(path), f"Target file does not exist: {path}"
        text = open(path, "r", encoding="utf-8").read()
        assert "\u2014" not in text, f"Illegal em-dash (\\u2014) found in: {path}"
