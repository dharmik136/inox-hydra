"""
Deleting media says what happened, and removes the file. [BE-18]

When the file could not be removed (held open by a viewer, OneDrive or
antivirus on Windows; here a read-only folder), the studio dropped the library
row and answered 200 "Asset ... deleted". The photo stayed on disk, hidden
from the studio, and went into every later backup. An id that never existed
was "deleted" too.
"""

import io
import os
import stat
import sys

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import app as app_module  # noqa: E402
import database  # noqa: E402
import paths  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    return TestClient(app_module.app)


def _upload(client):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "PNG")
    res = client.post("/api/media/upload", files={"file": ("private-photo.png", buf.getvalue(), "image/png")})
    assert res.status_code == 200, res.text
    body = res.json()
    return body["asset_id"], os.path.join(paths.get_assets_dir(), body["url"].replace("/assets/", ""))


def _listed(client, asset_id):
    return any(a["id"] == asset_id for a in client.get("/api/media").json()["assets"])


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="a read-only folder stops deletes only for an ordinary POSIX user")
def test_a_file_that_cannot_be_removed_is_reported_and_kept(client):
    asset_id, full = _upload(client)
    folder = os.path.dirname(full)
    os.chmod(folder, stat.S_IRUSR | stat.S_IXUSR)
    try:
        res = client.delete(f"/api/media/{asset_id}")
    finally:
        os.chmod(folder, stat.S_IRWXU)
    assert res.status_code == 409, res.text
    assert "could not be removed" in res.json()["detail"]
    assert os.path.exists(full)
    assert _listed(client, asset_id), "the row went while the file stayed"


def test_a_delete_removes_the_file_and_the_row(client):
    asset_id, full = _upload(client)
    res = client.delete(f"/api/media/{asset_id}")
    assert res.status_code == 200, res.text
    assert not os.path.exists(full)
    assert not _listed(client, asset_id)


def test_an_unknown_id_is_404(client):
    res = client.delete("/api/media/never-existed")
    assert res.status_code == 404
    assert "Nothing was deleted" in res.json()["detail"]
