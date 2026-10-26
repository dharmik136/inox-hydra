"""
An Activity line says what was read, when it was published, and when read.
==========================================================================

Three defects on one line of the Activity log (cycle 4, track 3, batch 0,
from the sections report's defects table):

- "Reposts" was left out when the captured count was 0, so a captured zero
  and a missing value drew the same, against the screen's own rule that a
  missing count must not read as 0. It now prints 0 when read and "not
  measured" when the bridge never read it, like the other three figures.
- A post was filed under last_seen_at, the day the bridge last read it,
  rather than under published_at, which the route also returns. It is now
  filed under its published day, and the line says when it was read.
- "Bridge: {carrier} (...)" could never render: the route read a key
  bridge_status never returns, so the fallback always showed. The dead
  branch is gone from the screen, the route and the type.
"""

import os
import re
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "ActivitySurface.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_activity_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def test_the_route_returns_no_carrier_it_never_knows(studio):
    answer = studio.get("/api/v1/self/activity-stream?limit=5")
    assert answer.status_code == 200, answer.text
    summary = answer.json()["summary"]
    assert "bridge_carrier" not in summary, "the route still returns a key that is always null"
    assert "bridge_connected" in summary and "bridge_last_seen" in summary


def test_the_screen_has_no_sentence_that_cannot_render():
    assert "bridge_carrier" not in _read(SURFACE)
    assert "bridge_carrier" not in _read(API)
    assert "Bridge: ${" not in _read(SURFACE)


def test_reposts_are_printed_whenever_they_were_read():
    source = _read(SURFACE)
    assert not re.search(r"if \(post\.reposts\)", source), "a captured zero still draws the same as a missing value"
    assert "`Reposts: ${measured(post.reposts)}`" in source


def test_a_post_is_filed_under_its_published_day_and_says_when_it_was_read():
    source = _read(SURFACE)
    assert re.search(r"at: post\.published_at \?\? post\.last_seen_at", source), "a post is still filed under the day it was last read"
    assert re.search(r"read \$\{ago\(post\.last_seen_at\)\}", source), "the line does not say when the post was read"
