"""
The Evidence panel reads its minimums from the engine, not from its own text.
=============================================================================

EvidencePanel.tsx said "Fewer than 3 settled posts" and "n >= 8 guard" in
its own words (cycle 4, track 3, batch 0, from the sections report's defects
table). results.py owns both numbers, MIN_FOR_MEDIAN and MIN_PER_SIDE, and
the one-definition rule exists because a number written into a screen stops
being true the day the engine's changes. The brief now carries both, and the
panel prints what it is handed.
"""

import os
import re
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

PANEL = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "EvidencePanel.tsx")


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc4_t3_evidence_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _posts(count, start=0):
    from database import get_db
    conn = get_db()
    with conn:
        for n in range(start, start + count):
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, '2026-08-01T09:00:00+00:00', ?, '2026-10-01', '2026-10-01')",
                         (f"urn:li:activity:738000000000000{n:04d}", f"Post {n}.\n\nIts body.", 10 + n * 5))
    conn.close()


def test_the_cold_start_brief_carries_the_minimums(home):
    import results
    from evidence_briefing import get_retrieval_evidence_brief
    brief = get_retrieval_evidence_brief()
    assert brief["has_evidence"] is False
    assert brief["min_settled_posts"] == results.MIN_FOR_MEDIAN
    assert brief["min_per_side"] == results.MIN_PER_SIDE


def test_the_brief_with_evidence_carries_the_minimums(home):
    import results
    from evidence_briefing import get_retrieval_evidence_brief
    _posts(4)
    brief = get_retrieval_evidence_brief()
    assert brief["has_evidence"] is True, brief
    assert brief["min_settled_posts"] == results.MIN_FOR_MEDIAN
    assert brief["min_per_side"] == results.MIN_PER_SIDE


def test_the_cold_start_is_judged_at_the_engines_minimum(home):
    """Two settled posts are below the median's minimum; three are not."""
    from evidence_briefing import get_retrieval_evidence_brief
    _posts(2)
    assert get_retrieval_evidence_brief()["has_evidence"] is False
    _posts(1, start=2)
    assert get_retrieval_evidence_brief()["has_evidence"] is True


def test_the_panel_writes_no_minimum_of_its_own():
    with open(PANEL, encoding="utf-8") as handle:
        source = handle.read()
    literal = re.findall(r"(?:Fewer than|at least|n\s*(?:&ge;|>=)|≥)\s*\d+", source)
    assert not literal, f"the panel carries its own minimum: {literal}"
    assert "min_settled_posts" in source and "min_per_side" in source, "the panel does not read the minimums it prints"
