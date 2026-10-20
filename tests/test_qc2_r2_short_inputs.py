"""
A short image concept or copilot draft gets a readable 422. [BE-16]

The image route allowed one character while the image agent's contract needs
three, so "AI", "5G" or "Go" answered 500 on Preview and failed Generate with
"1 validation error for ImagePromptInput ... https://errors.pydantic.dev/...".
The copilot (ten characters) had the same gap.
"""

import os
import sys

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", ["/api/image/synthesize-prompt", "/api/image/generate"])
@pytest.mark.parametrize("concept", ["AI", "5G", "  Go  "])
def test_a_short_image_concept_is_a_readable_422(client, path, concept):
    res = client.post(path, json={"concept": concept, "aspect_ratio": "1:1"})
    assert res.status_code == 422, res.text
    message = res.json()["detail"][0]["msg"]
    assert "at least 3 characters" in message
    assert "pydantic" not in res.text


def test_a_short_copilot_draft_is_a_422_not_a_500(client):
    res = client.post("/api/copilot/optimize", json={"raw_content": "short"})
    assert res.status_code == 422, res.text
    assert "pydantic" not in res.text
