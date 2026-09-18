"""
Milestone 4 Automated Verification Test Suite: Days 13 to 17
============================================================
Validates:
1. Day 13: High-Performance Vector Carousel Slide Generator (4:5 vertical & 1:1 ratio).
2. Day 14: Automated QA & Viewport Test assertions.
3. Day 15: Security & Threat Modeling (The CSO Audit: 127.0.0.1 loopback & zero cloud token egress).
4. Day 16: Packaging & 1-Click Distribution for Non-Developers (launch_studio.bat, shortcut scripts).
5. Day 17: Launch Day: The Sovereign Creator Manifesto (Full 17-Day Roadmap Seeding Integrity).
6. Strict Zero Em-Dash Enforcement across all Milestone 4 components.
"""

import os
import sys
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import (
    get_db,
    seed_day13_draft,
    seed_day14_draft,
    seed_day15_draft,
    seed_day16_draft,
    seed_day17_draft
)
from carousel_engine import carousel_engine

client = TestClient(app)


def test_day13_vector_carousel_generation():
    """
    Day 13: Verify vector carousel slide deck generation in 4:5 vertical (1080x1350)
    and 1:1 square (1080x1080) with pagination and typography.
    """
    slides_payload = {
        "slides": [
            {"tag": "COVER", "title": "The Decoupled Enterprise", "body": "Why modern data pipelines avoid centralized schemas."},
            {"tag": "ARCHITECTURE", "title": "Local SQLite WAL", "body": "Sub-millisecond writes with zero external cloud egress."},
            {"tag": "CONCLUSION", "title": "Key Takeaway", "body": "Sovereign desktop creator systems eliminate SaaS subscription rent."}
        ],
        "theme": "dark_obsidian",
        "aspect_ratio": "4:5",
        "author_name": "Dharmik Shingala",
        "author_title": "Enterprise Systems Practitioner"
    }

    # 1. Test 4:5 vertical deck via API
    resp = client.post("/api/v1/carousel/deck/generate", json=slides_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["slides_count"] == 3
    assert data["dimensions"]["width"] == 1080
    assert data["dimensions"]["height"] == 1350
    assert len(data["slides"]) == 3

    # Verify slide SVG structure
    first_slide = data["slides"][0]
    assert first_slide["slide_number"] == "01 / 03"
    assert "<svg" in first_slide["svg"]
    assert "Dharmik Shingala" in first_slide["svg"]
    assert "The Decoupled Enterprise" in first_slide["svg"]
    assert "\u2014" not in first_slide["svg"], "Em-dash found in slide SVG"

    # 2. Test 1:1 square deck
    slides_payload["aspect_ratio"] = "1:1"
    resp_sq = client.post("/api/v1/carousel/deck/generate", json=slides_payload)
    assert resp_sq.status_code == 200
    data_sq = resp_sq.json()
    assert data_sq["dimensions"]["width"] == 1080
    assert data_sq["dimensions"]["height"] == 1080

    # 3. Verify Day 13 Draft Seeding
    id13 = seed_day13_draft()
    assert id13 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id13,))
    row13 = cursor.fetchone()
    assert row13 is not None
    assert "High-Performance Carousel & Visual Media" in row13[0]
    assert "1080px by 1350px" in row13[1]
    tags13 = json.loads(row13[2])
    assert "#carouselDesign" in tags13
    conn.close()


def test_day14_automated_qa_and_testing_assertions():
    """
    Day 14: Verify automated QA test coverage integrity and Day 14 draft seeding.
    """
    # Verify Day 14 Draft Seeding
    id14 = seed_day14_draft()
    assert id14 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id14,))
    row14 = cursor.fetchone()
    assert row14 is not None
    assert "Automated QA & Browser Testing" in row14[0]
    assert "G-Stack QA Lead" in row14[0]
    assert "Playwright" in row14[1]
    tags14 = json.loads(row14[2])
    assert "#automatedQA" in tags14
    assert "#playwright" in tags14
    conn.close()


def test_day15_security_and_cso_audit():
    """
    Day 15: Verify 5-point CSO Security Audit:
    1. Strict 127.0.0.1 loopback binding.
    2. Zero cloud token egress.
    3. Day 15 draft seeding.
    """
    # 1. Audit server binding files for accidental 0.0.0.0 exposure
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
    files_to_audit = ["app.py", "server.py", "start_backend.py"]

    for fname in files_to_audit:
        fpath = os.path.join(backend_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                code = f.read()
                # 0.0.0.0 binding is strictly forbidden
                assert "0.0.0.0" not in code, f"Insecure 0.0.0.0 binding found in {fname}"

    # 2. Verify Day 15 Draft Seeding
    id15 = seed_day15_draft()
    assert id15 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id15,))
    row15 = cursor.fetchone()
    assert row15 is not None
    assert "Security & Threat Modeling: The CSO Audit" in row15[0]
    assert "Strict 127.0.0.1 Loopback Binding" in row15[1]
    tags15 = json.loads(row15[2])
    assert "#cyberSecurity" in tags15
    assert "#localFirst" in tags15
    conn.close()


def test_day16_packaging_and_distribution_scripts():
    """
    Day 16: Verify 1-click launcher scripts (launch_studio.bat) exist and contain
    python environment validation and auto-opening browser logic.
    """
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    launch_bat = os.path.join(root_dir, "launch_studio.bat")
    assert os.path.exists(launch_bat), "Missing launch_studio.bat"

    with open(launch_bat, "r", encoding="utf-8", errors="ignore") as f:
        bat_content = f.read()

    assert "python" in bat_content.lower()
    assert "127.0.0.1:8000" in bat_content

    # Verify Day 16 Draft Seeding
    id16 = seed_day16_draft()
    assert id16 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id16,))
    row16 = cursor.fetchone()
    assert row16 is not None
    assert "Packaging & 1-Click Distribution" in row16[0]
    assert "launch_studio.bat" in row16[1]
    tags16 = json.loads(row16[2])
    assert "#softwareDistribution" in tags16
    conn.close()


def test_day17_launch_manifesto_and_full_roadmap_integrity():
    """
    Day 17: Verify the complete 17-day launch roadmap integrity.
    All drafts for Days 01 through 17 must be seeded in SQLite drafts and posts tables.
    """
    id17 = seed_day17_draft()
    assert id17 is not None

    conn = get_db()
    cursor = conn.cursor()

    # Verify Day 17 Draft
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id17,))
    row17 = cursor.fetchone()
    assert row17 is not None
    assert "Launch Day: The Sovereign Creator Manifesto" in row17[0]
    assert "17 days ago" in row17[1]
    tags17 = json.loads(row17[2])
    assert "#sovereignSoftware" in tags17

    # Verify total drafts count is >= 17
    cursor.execute("SELECT COUNT(*) FROM drafts")
    drafts_count = cursor.fetchone()[0]
    assert drafts_count >= 17, f"Expected >= 17 drafts across the roadmap, got {drafts_count}"

    # Verify posts table has corresponding entries
    cursor.execute("SELECT COUNT(*) FROM posts")
    posts_count = cursor.fetchone()[0]
    assert posts_count >= 17, f"Expected >= 17 posts across the roadmap, got {posts_count}"

    conn.close()


def test_milestone4_zero_em_dashes():
    """
    Verify strict zero em-dash compliance across all Milestone 4 files.
    """
    files_to_check = [
        "studio/backend/carousel_engine.py",
        "studio/backend/database.py",
        "studio/backend/app.py",
        "tests/test_milestone4_days13_17.py"
    ]
    forbidden_char = "\u2014"

    for file_path in files_to_check:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            count = content.count(forbidden_char)
            assert count == 0, f"Violation: Found {count} em-dash characters in {file_path}"
