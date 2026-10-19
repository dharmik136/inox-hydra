"""
With no model set up, nothing the studio writes states a fact the creator did
not give. [WRITE-16]

The fallbacks were ready-to-apply openings in the creator's own voice: '80% of
teams are using X wrong', 'eliminated 90% of our production friction', 'until
you manage X across 12+ enterprise modules', and from the copilot 'Here is
what 10 years in enterprise architecture taught me about X'. A bakery owner
was handed another author's background and made-up numbers.

What may remain is structure: the creator's own words, and visible
[placeholders] where a fact of theirs has to go.
"""

import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

BAKERY = "We moved our bakery orders from WhatsApp to a simple form"

# Claims a template has no business making: numbers, tenure, an employer's
# scale, another author's field or title, results nobody measured.
INVENTED = re.compile(
    r"%|\b\d|\byears?\b|enterprise|architect|strategist|production|modules?\b|"
    r"\bour team\b|\bteams\b|eliminated|saved|hundreds|fire[- ]drills|24/7|"
    r"\bI have\b|\bI've\b|taught me|my job|schematic|walkthrough|\bseconds?\b",
    re.IGNORECASE,
)


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(provider="local_deterministic")
    yield


def _claims(text, given=""):
    """
    What the text claims that the creator's own words do not contain.

    A [placeholder] is the creator's to fill and list numbering is layout, so
    neither counts.
    """
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"(?m)^\s*\d+\.\s|\bStep \d+:", "", text)
    found = set(match.group(0).lower() for match in INVENTED.finditer(text))
    return {claim for claim in found if claim not in given.lower()}


@pytest.mark.parametrize("given", [BAKERY, "Pricing for small studios", ""])
def test_re_hook_templates_are_structure_and_the_creators_words(given):
    from repurposer import generate_10x_hooks

    hooks = generate_10x_hooks(given)
    assert len(hooks) == 10
    for hook in hooks:
        text = hook["hook_text"]
        assert not _claims(text, given), f"{hook['archetype']} invents {_claims(text, given)}: {text!r}"
        assert "[" in text and "]" in text, f"no visible placeholder, so it reads as finished: {text!r}"
        assert hook.get("source") == "template", hook


def test_the_copilot_without_a_model_invents_nothing():
    from agno_agentos.agents.content_copilot_agent import LinkedInContentCopilotAgent
    from agno_agentos.contracts import CopilotDraftInput

    agent = LinkedInContentCopilotAgent()
    for media in (None, "image", "carousel", "video"):
        result = agent.optimize(CopilotDraftInput(raw_content=BAKERY + ".", attached_media_type=media))
        for hook in result.hook_variants:
            assert not _claims(hook, BAKERY), f"copilot hook invents {_claims(hook, BAKERY)}: {hook!r}"
            assert "[" in hook, hook
        assert not _claims(result.optimized_content, BAKERY), result.optimized_content


def test_command_without_a_model_says_so_and_writes_nothing():
    from app import app

    client = TestClient(app)
    res = client.post("/api/ai/command", json={"command": "Write a post about " + BAKERY})
    assert res.status_code == 200
    body = res.json()
    assert "No model is set up" in body["output"], body
    assert not _claims(body["output"], BAKERY), body["output"]
    assert "Zero manual intervention" not in body["output"]


@pytest.mark.parametrize("given", [BAKERY, ""])
def test_repurpose_without_a_model_keeps_to_the_creators_text(given):
    from repurposer import repurpose_content

    frameworks = repurpose_content(given)
    assert len(frameworks) == 5
    for item in frameworks:
        assert not _claims(item["content"], given), f"{item['framework']} invents {_claims(item['content'], given)}"
        assert "[" in item["content"], item
        if given:
            assert given in item["content"], "the creator's own text is missing"


def test_the_audit_does_not_suggest_another_authors_hashtags():
    from repurposer import audit_linkedin_algorithm_safety

    advice = " ".join(audit_linkedin_algorithm_safety(BAKERY)["recommendations"])
    assert "#Enterprise" not in advice and "#Architecture" not in advice, advice
