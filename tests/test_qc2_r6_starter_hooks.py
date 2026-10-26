"""
A new creator starts on neutral hook forms; the engineering pack is opt-in.
===========================================================================

FRONTEND D-8: the Composer's hook rail opened with the original author's own
first-person claims ("I spent $2,400 on creator SaaS before realizing...",
"90% of software engineers misunderstand local-first architectures") under
an EDITOR'S RATING of 9.8, and Alt+1 made one the creator's opening line.
The Swipe File's categories were ARCHITECTURE, BENCHMARKS and REVERSE
ENGINEERING for everyone.

Owner decision (D5): neutral defaults, with an opt-in "engineering creator"
pack. A starter is a fill-in form, claims nothing, and carries no rating.
"""

import os
import re
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
import intelligence_sync  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)


@pytest.fixture
def library():
    """The template library as it was, put back afterwards."""
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM viral_templates")]
    conn.execute("DELETE FROM viral_templates")
    conn.commit()
    conn.close()
    yield
    conn = get_db()
    conn.execute("DELETE FROM viral_templates")
    for row in rows:
        columns = ", ".join(row)
        conn.execute(f"INSERT INTO viral_templates ({columns}) VALUES ({', '.join('?' for _ in row)})", tuple(row.values()))
    conn.commit()
    conn.close()


def _templates():
    return client.get("/api/v1/intelligence/templates?limit=200").json()["templates"]


def test_a_new_library_holds_only_neutral_fill_in_forms(library):
    templates = _templates()
    assert templates, "a new install has no hook forms at all"
    pack_hooks = {t["hook_text"] for t in intelligence_sync.ENGINEERING_PACK}
    for template in templates:
        assert template["hook_text"] not in pack_hooks, template["hook_text"]
        assert "[" in template["hook_text"], f"a starter that is not a fill-in form: {template['hook_text']}"
        assert template["velocity_score"] is None, "a starter carries a rating nobody measured"
        assert not re.search(r"\$\d|\d+%|\d{2,}ms", template["hook_text"]), template["hook_text"]
    archetypes = {t["archetype"] for t in templates}
    assert not archetypes & {"Architecture", "Benchmarks", "Reverse Engineering"}


def test_the_engineering_pack_is_added_and_removed_on_request(library):
    _templates()
    starters = len(_templates())

    added = client.post("/api/v1/intelligence/packs/engineering", json={"enabled": True})
    assert added.status_code == 200, added.text
    assert added.json()["added"] == len(intelligence_sync.ENGINEERING_PACK)
    again = client.post("/api/v1/intelligence/packs/engineering", json={"enabled": True})
    assert again.json()["added"] == 0, "adding the pack twice doubled it"
    assert len(_templates()) == starters + len(intelligence_sync.ENGINEERING_PACK)
    # The pack is recognised by its example id, which is how the retired swipe
    # wall told a pack form from a starter.
    assert sum(1 for t in _templates() if str(t["example_post_id"]).startswith("blueprint-")) == len(
        intelligence_sync.ENGINEERING_PACK)

    removed = client.post("/api/v1/intelligence/packs/engineering", json={"enabled": False})
    assert removed.status_code == 200
    assert removed.json()["removed"] == len(intelligence_sync.ENGINEERING_PACK)
    assert len(_templates()) == starters


def test_an_existing_library_keeps_the_pack_it_has(library):
    intelligence_sync.intelligence_sync_engine.seed_offline_templates(templates=intelligence_sync.ENGINEERING_PACK)
    before = len(_templates())
    intelligence_sync.intelligence_sync_engine._ensure_offline_seeded()
    assert len(_templates()) == before, "an install that had the pack lost or gained forms on its own"


def test_the_rail_hides_a_rating_that_is_not_there():
    """
    The wall half of this read SwipeSurface.tsx, which cycle 3 batch T7
    removed: the rail is now the only surface that draws these rows.
    """
    root = os.path.join(os.path.dirname(__file__), "..", "studio", "ui", "src", "components")
    rail = open(os.path.join(root, "HookFilmstrip.tsx")).read()
    assert "template.velocity_score === null" in rail or "template.velocity_score == null" in rail
