"""
The Evidence panel says where its contrasts go, which is nowhere.
=================================================================

The panel said "These exact contrast ratios and exemplar posts are injected
directly into your BYO-AI Copilot prompt context". The brief is added to a
prompt only in the copilot agent, which is reachable only from
/api/copilot/optimize, which no interface file calls; Re-Hook and Command
add the voice pack and nothing else (cycle 4, track 3, batch 0, from the
sections report's defects table). A creator deciding what to share was told
more left the machine than did.

The sentence now says what is sent, and this holds the sentence to the
code: if a screen starts calling the copilot route, or Re-Hook starts
reading the evidence brief, the sentence is wrong again and this fails.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PANEL = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "EvidencePanel.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")
REPURPOSER = os.path.join(REPO_ROOT, "studio", "backend", "repurposer.py")
AI_ROUTER = os.path.join(REPO_ROOT, "studio", "backend", "routers", "ai.py")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_no_screen_calls_the_copilot_route():
    """The only path that puts the brief into a prompt has no caller in the interface."""
    assert "/api/copilot/optimize" in _read(AI_ROUTER), "the copilot route moved; re-read what the panel claims"
    assert "/api/copilot" not in _read(API), (
        "a screen now calls the copilot route, so the Evidence panel's sentence about where its contrasts go "
        "must be rewritten"
    )


def test_rehook_and_command_send_the_voice_pack_and_not_the_brief():
    source = _read(REPURPOSER)
    assert "voice_pack" in source
    assert "evidence_briefing" not in source and "get_retrieval_evidence_brief" not in source, (
        "Re-Hook or Command now reads the evidence brief, so the Evidence panel's sentence must say so"
    )


def test_the_panel_does_not_claim_an_injection_that_never_happens():
    source = _read(PANEL)
    for claim in ("injected directly", "Copilot prompt context", "Active Copilot Grounding"):
        assert claim not in source, f"the panel still claims {claim!r}"
    assert "Nothing in the Composer sends" in source
    assert "voice pack" in source, "the panel does not say what Re-Hook and Command do send"
