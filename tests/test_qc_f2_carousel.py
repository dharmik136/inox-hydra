"""
Carousel slides render their text in the theme's colours, and say nothing the
creator did not give. [WRITE-26, WRITE-27]

WRITE-26: the title and body sit in an HTML foreignObject but were coloured
with the SVG `fill` property, which HTML text ignores, so they rendered black,
nearly invisible on the default dark theme.

WRITE-27: an untagged slide was headed ARCHITECTURE, the original author's
niche, and a deck with no Brand Studio name was signed "Creator".
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from carousel_engine import THEMES, carousel_engine  # noqa: E402


def _rgb(hex_colour):
    value = hex_colour.lstrip("#")
    return "rgb({}, {}, {})".format(*(int(value[i:i + 2], 16) for i in (0, 2, 4)))


@pytest.fixture(scope="module")
def chromium():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        yield context.new_page()
        context.close()
        browser.close()


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_slide_text_renders_in_the_theme_colours(chromium, theme):
    svg = carousel_engine.render_slide_svg(
        {"title": "One clear title", "body": "A body line the reader must be able to see."},
        0, 3, theme_name=theme,
    )
    chromium.set_content(f"<!doctype html><html><body style='margin:0'>{svg}</body></html>")
    title = chromium.eval_on_selector("h1.title", "node => getComputedStyle(node).color")
    body = chromium.eval_on_selector("p.body", "node => getComputedStyle(node).color")
    assert title == _rgb(THEMES[theme]["text_primary"]), f"{theme} title renders {title}"
    assert body == _rgb(THEMES[theme]["text_body"]), f"{theme} body renders {body}"


def _text_nodes(svg):
    return {cls: text for cls, text in re.findall(r'<text[^>]*class="([^"]+)"[^>]*>([^<]*)</text>', svg)}


def test_an_untagged_unsigned_slide_carries_no_invented_label():
    svg = carousel_engine.render_slide_svg({"title": "One", "body": "Body"}, 0, 1)
    nodes = _text_nodes(svg)
    assert "ARCHITECTURE" not in svg
    assert "Creator" not in svg
    assert "tag" not in nodes, f"an empty tag is still drawn: {nodes}"
    assert "author" not in nodes and "author-sub" not in nodes, f"an empty signature is still drawn: {nodes}"


def test_the_deck_endpoint_signs_nothing_without_a_name(monkeypatch):
    from fastapi.testclient import TestClient
    from app import app

    res = TestClient(app).post("/api/v1/carousel/deck/generate", json={"slides": [{"title": "One", "body": "Body"}]})
    assert res.status_code == 200, res.text
    blob = res.text
    assert "ARCHITECTURE" not in blob
    assert ">Creator<" not in blob


def test_a_given_tag_and_name_are_still_drawn():
    svg = carousel_engine.render_slide_svg(
        {"title": "One", "body": "Body", "tag": "Pricing"}, 0, 1, author_name="Asha Rao", author_title="Founder"
    )
    nodes = _text_nodes(svg)
    assert nodes.get("tag") == "Pricing"
    assert nodes.get("author") == "Asha Rao"
    assert nodes.get("author-sub") == "Founder"
