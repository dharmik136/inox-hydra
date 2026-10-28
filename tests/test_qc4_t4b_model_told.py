"""
The Composer says what the model is told.
=========================================

Batch 8 of the sections report: the routes held each piece a writing
request carries, and the client dropped them. The Prompt tab said which
features send what and named the voice pack's parts; it never showed the
words. Now "What the model is told" shows the pack as it is appended (who
you are, your habits measured across N posts, your openers by the studio's
one ranking), the phrases the studio will not let a model write and where
that is checked, whether your grounding sources go with any Composer request
(none do), and how an image prompt is made.

Every part is read from the code that builds the request, so the panel and
the request cannot say two things.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
PANEL = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PromptPanel.tsx")


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_told_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        for days, text in ((30, "Why does dispatch slow down on Mondays?\n\nIt is the handovers."),
                           (40, "Most outages start with a spreadsheet nobody owns."),
                           (50, "A short note on saying no. #operations"),
                           (60, "We cut dispatch time by a third.")):
            at = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at, "
                         "reactions) VALUES (?, ?, ?, ?, ?, ?)",
                         (f"urn:li:activity:73900000000009{days:02d}", text, at, at, at, days))
    conn.close()
    from fastapi.testclient import TestClient
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _told(client):
    answer = client.get("/api/v1/composer/told")
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_voice_pack_is_shown_as_it_is_appended(client):
    import voice_pack
    told = _told(client)
    voice = told["voice"]
    assert voice["posts_measured"] == 4
    assert voice["habits"][0] == "Measured across 4 of their posts:"
    block = voice_pack.prompt_block()
    for line in voice["habits"] + voice["openers"] + voice["who"]:
        assert line in block, f"the panel shows a line the request does not carry: {line!r}"
    assert voice["openers_rule"] and "settled" in voice["openers_rule"]


def test_the_phrases_a_model_may_not_write_are_the_studios_list(client):
    from agno_agentos.scar_tissue import BANNED_TROPES
    import repurposer
    scar = _told(client)["scar_tissue"]
    assert scar["phrases"] == list(BANNED_TROPES)
    assert scar["checked_on"] == ["image prompts"]
    assert scar["named_in_command"] == list(repurposer.COMMAND_CLICHES)


def test_grounding_says_no_composer_request_carries_it(client):
    grounding = _told(client)["grounding"]
    assert grounding["sent_with"] == [], "a Composer request is said to carry grounding it does not gather"
    assert grounding["sources_on"] == 0


def test_the_prompt_tab_draws_what_the_model_is_told():
    with io.open(PANEL, encoding="utf-8") as handle:
        panel = handle.read()
    assert "What the model is told" in panel and "fetchModelTold" in panel
    for field in ("voice.habits", "voice.openers", "scar_tissue.phrases", "grounding.sources_on", "images."):
        assert field in panel, f"the panel does not draw {field}"
