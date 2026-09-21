"""
Media Studio & Unified Dropzone Test Suite
==========================================
Tests multipart file uploads for Images, Multi-Slide PDF Carousels, and Videos.
Verifies MIME validation, local disk persistence, SQLite media_assets tracking, and deletion.
"""

import io
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import app
from database import init_db, get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_upload_image_media():
    """Tests uploading PNG image through the media dropzone."""
    # Create minimal 1x1 PNG bytes
    png_bytes = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xbf'
        b'\x04\x00\x05\x00\x01\r\x0b\x9a\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    files = {"file": ("architecture_diagram.png", io.BytesIO(png_bytes), "image/png")}
    resp = client.post("/api/media/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["media_type"] == "image"
    assert "architecture_diagram.png" in data["filename"]
    assert data["url"].startswith("/assets/uploads/")
    assert data["size_bytes"] == len(png_bytes)


def test_upload_pdf_carousel_media():
    """Tests uploading PDF document carousel through the media dropzone."""
    pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 1080 1080]>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000102 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n162\n%%EOF"
    files = {"file": ("enterprise_playbook.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post("/api/media/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["media_type"] == "carousel"
    assert data["page_count"] >= 1
    assert data["url"].endswith(".pdf")


def test_upload_video_media():
    """Tests uploading MP4 video through the media dropzone."""
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 200
    files = {"file": ("demo_walkthrough.mp4", io.BytesIO(fake_mp4), "video/mp4")}
    resp = client.post("/api/media/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["media_type"] == "video"
    assert data["url"].endswith(".mp4")


def test_upload_unsupported_mime_rejected():
    """Verifies that invalid extensions (e.g. .exe, .sh) are safely rejected."""
    files = {"file": ("malicious.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-msdownload")}
    resp = client.post("/api/media/upload", files=files)
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_list_and_delete_media():
    """Tests listing uploaded media and deleting an asset."""
    # First upload an asset
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    files = {"file": ("temp_test_to_delete.png", io.BytesIO(png_bytes), "image/png")}
    up_resp = client.post("/api/media/upload", files=files)
    asset_id = up_resp.json()["asset_id"]

    # List
    list_resp = client.get("/api/media")
    assert list_resp.status_code == 200
    assets = list_resp.json()["assets"]
    assert any(a["id"] == asset_id for a in assets)

    # Delete
    del_resp = client.delete(f"/api/media/{asset_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"

    # Confirm removed
    list_resp_after = client.get("/api/media")
    assert not any(a["id"] == asset_id for a in list_resp_after.json()["assets"])


def test_upload_zero_byte_file_rejected():
    """Verifies that an empty 0-byte file is rejected with 400 Bad Request."""
    files = {"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
    resp = client.post("/api/media/upload", files=files)
    assert resp.status_code == 400
    assert "empty (0 bytes)" in resp.json()["detail"]


def test_upload_disguised_file_rejected():
    """Verifies that a text file renamed to .pdf or .png is rejected by signature validation."""
    fake_pdf = b"This is plain text pretending to be a PDF."
    files_pdf = {"file": ("fake_doc.pdf", io.BytesIO(fake_pdf), "application/pdf")}
    resp_pdf = client.post("/api/media/upload", files=files_pdf)
    assert resp_pdf.status_code == 400
    assert "Invalid PDF format" in resp_pdf.json()["detail"]

    fake_png = b"Not a PNG image at all."
    files_png = {"file": ("fake_image.png", io.BytesIO(fake_png), "image/png")}
    resp_png = client.post("/api/media/upload", files=files_png)
    assert resp_png.status_code == 400
    assert "Invalid PNG format" in resp_png.json()["detail"]

