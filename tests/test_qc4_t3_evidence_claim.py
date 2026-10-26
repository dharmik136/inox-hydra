"""
The Evidence panel says what goes to the model from it, and what does not.
=========================================================================

The panel first claimed its contrasts and exemplars were "injected directly
into your BYO-AI Copilot prompt context"; the brief reaches a prompt only
through the copilot agent, which no interface file calls (cycle 4, track 3,
batch 0). The replacement said nothing on the tab was sent, which was false
the other way (review round 2, B1): Re-Hook and Command append the voice
pack to every prompt, and its openers are the opening lines of the posts the
panel lists as its top exemplars, both chosen by results.ranking. With a
provider connected, those opening lines leave the machine.

The sentence now says exactly that, and these tests hold it to the code: the
openers the voice pack sends are read on a seeded history and compared with
the exemplars the brief lists, so the sentence cannot drift from what is
sent in either direction.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

PANEL = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "EvidencePanel.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
REPURPOSER = os.path.join(REPO_ROOT, "studio", "backend", "repurposer.py")
AI_ROUTER = os.path.join(REPO_ROOT, "studio", "backend", "routers", "ai.py")
HELP = os.path.join(REPO_ROOT, "docs", "help", "connect-your-own-ai-provider.md")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def history(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_claim_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    now = datetime.now(timezone.utc)
    conn = get_db()
    with conn:
        for n in range(12):
            when = now - timedelta(days=12 + n * 3)
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (f"urn:li:activity:{(int(when.timestamp() * 1000) << 22) + n}",
                          f"Opening line of post {n}.\n\nThe rest of post {n}.", when.isoformat(), 10 + (n * 37) % 90,
                          now.isoformat(), now.isoformat()))
        # Three hours old, with the most reactions of all: too young for the
        # one ranking, so it is neither listed nor sent. Ranked by raw
        # reactions it would be sent and not listed, which is the drift the
        # guard below catches.
        young = now - timedelta(hours=3)
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                     "VALUES (?, 'A post from this morning.\n\nThe rest.', ?, 900, ?, ?)",
                     (f"urn:li:activity:{(int(young.timestamp() * 1000) << 22) + 99}", young.isoformat(),
                      now.isoformat(), now.isoformat()))
    conn.close()
    yield home
    shutil.rmtree(home, ignore_errors=True)


def test_the_openers_sent_are_the_exemplars_this_panel_lists(history):
    """What the sentence claims, read from what is actually sent."""
    import evidence_briefing
    import voice_pack
    brief = evidence_briefing.get_retrieval_evidence_brief()
    listed = [exemplar["text"].splitlines()[0] for exemplar in brief["top_exemplars"]]
    block = voice_pack.prompt_block()
    sent = [line[3:-1] for line in block.splitlines() if line.startswith('- "')]
    assert sent, "the voice pack sends no openers, so the panel's sentence that it does is false"
    assert set(sent) <= set(listed), f"the openers sent {sent} are not the exemplars the panel lists {listed}"
    assert any("opening lines" in item for item in voice_pack.disclosure()), "the disclosure no longer names the openers"
    # The figures and the contrasts are not in it: only words of the creator's.
    assert "reactions" not in "\n".join(line for line in block.splitlines() if line.startswith('- "'))
    assert "went with" not in block and "higher engagement" not in block


def test_rehook_and_command_send_the_voice_pack_and_not_the_brief():
    source = _read(REPURPOSER)
    assert "prompt_block" in source, "Re-Hook and Command no longer append the voice pack; rewrite the panel's sentence"
    assert "evidence_briefing" not in source and "get_retrieval_evidence_brief" not in source, (
        "Re-Hook or Command now reads the evidence brief, so the panel's sentence must say the contrasts are sent"
    )


def test_no_screen_calls_the_copilot_route():
    """The only path that puts the whole brief into a prompt has no caller in the interface."""
    assert "/api/copilot/optimize" in _read(AI_ROUTER), "the copilot route moved; re-read what the panel claims"
    assert "/api/copilot" not in _read(API), (
        "a screen now calls the copilot route, so the Evidence panel's sentence about what is sent must change"
    )


def test_the_panel_says_what_is_sent_and_what_stays():
    # Whitespace folded, because a sentence in JSX wraps across lines.
    source = " ".join(_read(PANEL).split())
    for wrong in ("injected directly", "Copilot prompt context", "Active Copilot Grounding",
                  "Nothing in the Composer sends", "what is on this tab stays on this machine"):
        assert wrong not in source, f"the panel still says {wrong!r}"
    assert "opening lines of your strongest posts" in source, "the panel does not say the openers are sent"
    assert "Re-Hook and Command" in source and "AI provider" in source
    assert "contrasts and figures on this tab stay on this machine" in source, (
        "the panel does not say what stays")
    # The help says the same thing in its own words.
    assert "the opening lines of your 3 most-reacted posts" in _read(HELP)
