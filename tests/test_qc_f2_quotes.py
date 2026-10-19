"""
A generated image carries only a quote the creator typed, attributed to whom
they typed. [WRITE-29]

Naming Seneca drew "Luck is what happens when preparation meets opportunity."
under his name, a line with no source in his writings, and Marcus Aurelius got
a modern paraphrase presented as a quotation. Any quoted phrase in a
description was signed "Leadership". A creator posting the image published a
misattribution under their own name.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from agno_agentos.agents.image_prompt_agent import ImagePromptSynthesizerAgent  # noqa: E402
from agno_agentos.contracts import ImagePromptInput  # noqa: E402
from agno_agentos.model_gateway import AIProviderConfig  # noqa: E402


def _synthesize(**fields):
    agent = ImagePromptSynthesizerAgent(ai_config=AIProviderConfig(provider="local_deterministic"))
    return agent.synthesize(ImagePromptInput(**fields))


@pytest.mark.parametrize("concept", [
    "a stoic study at dawn, Seneca",
    "Marcus Aurelius at a desk by a window",
    "Steve Jobs style minimal stage",
    "i need quote based on socrates in a quiet dark and white room",
])
def test_a_famous_name_draws_no_quote(concept):
    result = _synthesize(concept=concept)
    assert result.quote_text is None, f"{concept!r} was given the quote {result.quote_text!r}"
    assert result.quote_author is None, f"{concept!r} was attributed to {result.quote_author!r}"


def test_a_quote_in_the_description_is_used_but_not_signed_by_anyone_invented():
    result = _synthesize(concept='"Make the next step obvious" in a quiet studio')
    assert result.quote_text == "Make the next step obvious"
    assert result.quote_author is None


def test_a_typed_quote_and_author_are_used_as_typed():
    result = _synthesize(
        concept="a quiet studio", custom_quote_text="Ship the small thing.", custom_quote_author="Asha Rao"
    )
    assert (result.quote_text, result.quote_author) == ("Ship the small thing.", "Asha Rao")


def test_a_quote_request_still_keeps_the_frame_clear_and_drops_the_bust():
    """What the quote layout was for survives without the invented quote."""
    result = _synthesize(concept="i need quote based on socrates in a quiet dark and white room")
    assert "marble bust" in result.negative_prompt.lower()
    assert "socrates" not in result.master_prompt.lower()
    assert "negative space" in result.master_prompt.lower()
