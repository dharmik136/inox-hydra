import os
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))

from carousel_generator import (
    generate_carousel_pdf,
    wrap_text,
    get_font,
    MAX_CAROUSEL_SLIDES,
)
from docs_engine import (
    search_docs_fts,
    init_docs_search_index,
)
from app import app

client = TestClient(app)


def test_carousel_generator_null_and_invalid_slides():
    """generate_carousel_pdf strictly validates slides_data structure and bounds."""
    # Non-list input
    with pytest.raises(TypeError):
        generate_carousel_pdf(None)  # type: ignore

    with pytest.raises(TypeError):
        generate_carousel_pdf("not_a_list")  # type: ignore

    # Empty list
    with pytest.raises(ValueError, match="at least 1 slide"):
        generate_carousel_pdf([])

    # Exceeding MAX_CAROUSEL_SLIDES (30)
    huge_slides = [{"title": f"S{i}", "body": "B"} for i in range(MAX_CAROUSEL_SLIDES + 1)]
    with pytest.raises(ValueError, match="Too many slides"):
        generate_carousel_pdf(huge_slides)

    # Non-dict slide element
    with pytest.raises(TypeError, match="must be a dictionary"):
        generate_carousel_pdf([{"title": "Valid"}, None])  # type: ignore


def test_carousel_generator_em_dash_sanitization_and_render():
    """generate_carousel_pdf sanitizes em-dashes and produces valid PDF binary bytes."""
    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    slides = [
        {"title": f"Cover Slide{em_dash}Architecture", "body": f"First principles{en_dash}always."},
        {"title": "Step 01", "body": "Verify each component in isolation."},
        {"title": "Summary", "body": "Enterprise grade execution."},
    ]
    pdf = generate_carousel_pdf(slides, theme_name="engineering_blue")
    assert isinstance(pdf, bytes)
    assert len(pdf) > 20000
    assert pdf.startswith(b"%PDF")


def test_carousel_generator_fallback_theme_and_author():
    """generate_carousel_pdf cleanly handles unknown themes and missing author data."""
    slides = [{"title": "Single Slide", "body": "Clean test."}]
    pdf = generate_carousel_pdf(
        slides,
        author_name=None,  # type: ignore
        author_title=None,  # type: ignore
        theme_name="unknown_theme_xyz",
    )
    assert pdf.startswith(b"%PDF")


def test_carousel_generator_wrap_text_resilience():
    """wrap_text handles None and empty inputs cleanly."""
    font = get_font(20)
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (100, 100))
    draw = ImageDraw.Draw(img)

    assert wrap_text(None, font, 200, draw) == []
    assert wrap_text("", font, 200, draw) == []
    wrapped = wrap_text("Short single line", font, 500, draw)
    assert len(wrapped) == 1


def test_docs_engine_search_fts_null_and_types():
    """search_docs_fts handles null, non-string, or empty queries cleanly."""
    assert search_docs_fts(None) == []
    assert search_docs_fts(12345) == []  # type: ignore
    assert search_docs_fts("") == []
    assert search_docs_fts("   ") == []


def test_docs_engine_search_fts_limit_clamping():
    """search_docs_fts bounds limits to [1, 100]."""
    # Negative limit defaults or clamps
    res_neg = search_docs_fts("architecture", limit=-5)
    assert isinstance(res_neg, list)

    # Huge limit clamped without error
    res_huge = search_docs_fts("architecture", limit=500)
    assert isinstance(res_huge, list)


def test_docs_engine_missing_directory():
    """init_docs_search_index returns 0 for non-existent directories."""
    count = init_docs_search_index(docs_dir="C:\\non_existent_folder_xyz_123")
    assert count == 0


def test_docs_engine_em_dash_sanitization_in_indexing():
    """init_docs_search_index dynamically sanitizes em-dashes from indexed markdown."""
    em_dash = chr(0x2014)
    with tempfile.TemporaryDirectory() as tmpdir:
        md_file = os.path.join(tmpdir, "test_doc.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# Heading One\nSection content with an em-dash{em_dash}here.\n")

        count = init_docs_search_index(docs_dir=tmpdir)
        assert count >= 1

        results = search_docs_fts("content", limit=5)
        for r in results:
            assert em_dash not in r["snippet"]


def test_app_docs_search_api_bounds():
    """FastAPI docs search endpoint returns bounded results and handles empty query."""
    res_empty = client.get("/api/docs/search?q=")
    assert res_empty.status_code == 200
    assert res_empty.json()["count"] == 0

    res_valid = client.get("/api/docs/search?q=system&limit=500")
    assert res_valid.status_code == 200
    assert res_valid.json()["count"] <= 100


def test_app_get_doc_module_path_traversal():
    """FastAPI get_doc_module endpoint sanitizes IDs and rejects path traversal."""
    res_traversal = client.get("/api/docs/..%2F..%2Fetc%2Fpasswd")
    assert res_traversal.status_code == 404

    res_invalid = client.get("/api/docs/___invalid_mod___")
    assert res_invalid.status_code == 404


def test_zero_em_dash_compliance_module12():
    """Verify zero em-dash (0x2014) characters exist in Module 12 files."""
    em_dash = chr(0x2014)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(base_dir, "studio", "backend", "carousel_generator.py"),
        os.path.join(base_dir, "studio", "backend", "docs_engine.py"),
        os.path.abspath(__file__),
    ]

    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert em_dash not in content, f"Em-dash found in {file_path}"
