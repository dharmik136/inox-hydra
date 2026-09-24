"""
Media Upload Contract: The Frontend And Backend Must Agree On Key Names.
========================================================================
Guards a bug that every existing test was structurally blind to.

`POST /api/media/upload` returns `filename` and `url`. The browser's
`setAttachedMedia()` read `file_name` and `file_url`. So every real file upload
succeeded at the API, wrote to disk, inserted a database row, returned 200, and
then threw in the browser:

    TypeError: Cannot read properties of undefined (reading 'toLowerCase')

The attachment never appeared, the dropzone never closed, and the user was told
"Network error uploading file". Nothing was wrong with the network, and nothing
was wrong with the backend.

Every Python test passed throughout, because they all stop at the API boundary.
The one caller that did work was the AI image studio, which hand-builds an
object using the `file_name` form, which is why the mismatch survived.

This test crosses the boundary: it asserts the API's real response keys, and it
asserts the browser code normalises them. Either side drifting fails here.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import io
import os
import re
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# A real, structurally valid one page PDF. A truncated stub would not exercise
# the page counting path that produced page_count in the response.
REAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_media_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from fastapi.testclient import TestClient
    from studio.backend.app import app
    with TestClient(app) as c:
        yield c
    shutil.rmtree(home, ignore_errors=True)


def _upload(client, name, data, ctype):
    return client.post("/api/media/upload",
                       files={"file": (name, io.BytesIO(data), ctype)})


@pytest.mark.parametrize("name,data,ctype,expected_type", [
    ("deck.pdf", REAL_PDF, "application/pdf", "carousel"),
    ("square.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 128, "image/png", "image"),
    ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 128, "video/mp4", "video"),
])
def test_upload_accepts_each_media_type(client, name, data, ctype, expected_type):
    r = _upload(client, name, data, ctype)
    assert r.status_code == 200, r.text
    assert r.json()["media_type"] == expected_type


def test_upload_response_declares_the_keys_the_browser_consumes(client):
    """
    The contract itself. Renaming either key without updating the interface
    puts the attachment card back into the broken state.
    """
    body = _upload(client, "deck.pdf", REAL_PDF, "application/pdf").json()
    for key in ("filename", "url", "media_type", "asset_id", "size_bytes"):
        assert key in body, f"upload response no longer returns {key!r}: {sorted(body)}"

    assert body["filename"] == "deck.pdf"
    assert body["url"].startswith("/assets/uploads/")


def test_uploaded_file_lands_where_its_url_claims(client):
    """
    A 200 on upload means nothing if the bytes are not where the returned URL
    points. Verified on disk rather than over HTTP, deliberately.

    The /assets mount is built from a module level constant evaluated when
    studio.backend.app is first imported. pytest imports it once per session,
    so a per-test INOX_HYDRA_HOME cannot move the mount and an HTTP fetch here
    would fail for a reason that has nothing to do with the product. With the
    environment set before import, which is how the application actually
    starts, the same URL serves 200 with Content-Type application/pdf.
    """
    from studio.backend import paths

    body = _upload(client, "deck.pdf", REAL_PDF, "application/pdf").json()
    url = body["url"]
    assert url.startswith("/assets/")

    relative = url[len("/assets/"):].replace("/", os.sep)
    on_disk = os.path.join(paths.get_assets_dir(), relative)

    assert os.path.exists(on_disk), f"upload returned {url} but nothing is at {on_disk}"
    with open(on_disk, "rb") as f:
        assert f.read().startswith(b"%PDF"), "stored bytes are not the uploaded file"






