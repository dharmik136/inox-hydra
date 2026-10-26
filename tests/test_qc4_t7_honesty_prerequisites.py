"""
Nothing the daily section shows may inherit a second ranking or a manufactured count.
======================================================================================

Cycle 4, track 7, batch 0 of the personalised daily ideas report. Three things
the section could have inherited, each with the repository's own earlier
decision behind it:

  the openers        voice_pack._openers ordered by raw own_posts.reactions
                     with no settled rule, the one ranking left outside
                     results.py; it goes through results.ranking now
                     (tests/test_voice_pack.py holds the behaviour)
  /api/inspirations  served viral_templates under the retired Swipe File's
                     name with counts manufactured at render time and set
                     to None; nothing called it; it is gone
  the harvester      SwipeFileHarvesterAgent returned the same canned
                     "blueprint" for every post, took another person's post
                     and name as input, and had no route; it is gone, with
                     its contracts and its registry entry

And the boot-time recreation: init_db ran CREATE TABLE IF NOT EXISTS
inspirations before the ledger, so the table migration 2 dropped came back
empty on every boot. The baseline fingerprint records its absence.
"""

import io
import os
import re
import sqlite3
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)


def _read(*parts):
    with io.open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def test_init_db_does_not_recreate_the_table_migration_2_drops(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    import paths
    from database import init_db

    init_db()
    conn = sqlite3.connect(paths.get_db_path())
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert "inspirations" not in tables
    assert "viral_templates" in tables, "the hook rail's own table must survive"


def test_the_baseline_fingerprint_records_the_absence():
    import json

    baseline = json.loads(_read("studio", "backend", "schema_baseline.json"))
    assert "inspirations" not in baseline["tables"]


def test_the_inspirations_route_is_gone():
    import app as app_module
    from fastapi.testclient import TestClient

    client = TestClient(app_module.app)
    assert client.get("/api/inspirations").status_code == 404
    source = _read("studio", "backend", "app.py")
    assert "/api/inspirations" not in source


def test_the_harvester_is_deleted_not_unlinked():
    assert not os.path.exists(os.path.join(BACKEND, "agno_agentos", "agents", "swipe_harvester_agent.py"))
    for root, dirs, names in os.walk(os.path.join(REPO_ROOT, "studio")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "frontend_next")]
        for name in names:
            if name.endswith((".py", ".ts", ".tsx", ".js")):
                source = _read(os.path.join(root, name))
                assert "SwipeFileHarvesterAgent" not in source, f"{name} still names the harvester"
                assert "analyze_swipe" not in source, f"{name} still calls the harvester"
    from agno_agentos.registry import AGENT_REGISTRY

    assert "swipe_harvester" not in AGENT_REGISTRY


def test_no_module_ranks_openers_by_raw_reactions():
    """
    The guard with teeth: results.ranking is the one ranking of posts, and
    the voice pack reads it. Falsified by planting the old ORDER BY in a copy
    of the module source, which this detects.
    """
    source = _read("studio", "backend", "voice_pack.py")
    assert not re.search(r"ORDER BY\s+reactions", source), "a second ranking of posts is back"
    assert "results.ranking(" in source
    planted = source.replace("results.ranking(conn)", "conn.execute('SELECT 1 ORDER BY reactions DESC')")
    assert re.search(r"ORDER BY\s+reactions", planted), "the guard would not notice the old ranking"
