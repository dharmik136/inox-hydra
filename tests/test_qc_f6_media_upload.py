"""
Media Upload: Bounded, Whatever the Creator Drops In.
=====================================================

LinkedIn takes videos of several gigabytes, and the media library used to read
the whole upload into memory with no size limit, so a large enough file could
take the studio down mid-session. These hold the route to a size cap per kind
and to copying the file in chunks.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import app as app_module  # noqa: E402
from studio.backend import database, paths  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    return TestClient(app_module.app)


def _upload(client, name, data, ctype):
    return client.post("/api/media/upload", files={"file": (name, io.BytesIO(data), ctype)})


def test_an_upload_over_its_cap_is_refused_and_nothing_is_kept(client, monkeypatch):
    monkeypatch.setitem(app_module.MEDIA_UPLOAD_CAPS, "image", 4096)
    res = _upload(client, "too-big.png", PNG + b"\x00" * 4089, "image/png")
    assert res.status_code == 413, res.text
    assert "4 KB" in res.json()["detail"] or "4.0 KB" in res.json()["detail"]
    assert os.listdir(paths.get_uploads_dir()) == [], "a refused upload was left on disk"

    exactly = _upload(client, "fits.png", PNG + b"\x00" * 4088, "image/png")
    assert exactly.status_code == 200, exactly.text
    assert exactly.json()["size_bytes"] == 4096


def test_an_upload_is_copied_in_chunks_not_read_whole(client, monkeypatch):
    sizes = []
    real_read = UploadFile.read

    async def recording_read(self, size=-1):
        sizes.append(size)
        return await real_read(self, size)

    monkeypatch.setattr(UploadFile, "read", recording_read)
    data = b"\x00\x00\x00\x18ftypmp42" + os.urandom(3 * 1024 * 1024)
    res = _upload(client, "clip.mp4", data, "video/mp4")
    assert res.status_code == 200, res.text
    assert res.json()["size_bytes"] == len(data)
    assert sizes and all(0 < size <= 1024 * 1024 for size in sizes), f"read sizes: {sizes}"
    stored = os.path.join(paths.get_uploads_dir(), os.path.basename(res.json()["url"]))
    with open(stored, "rb") as handle:
        assert handle.read() == data


def test_each_kind_has_a_cap_no_smaller_than_linkedin_allows():
    caps = app_module.MEDIA_UPLOAD_CAPS
    assert caps["carousel"] >= 100 * 1024 * 1024
    assert caps["video"] >= 5 * 1024 * 1024 * 1024
    assert caps["image"] >= 20 * 1024 * 1024
