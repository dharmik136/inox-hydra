"""
Quality cycle 2026-10, batch F7: what the interface tells a creator, held to
what the product does.

These read the components' rendered text (comments removed), because the
claims are copy: a sentence on screen that a buyer relies on.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")


def _rendered(name):
    with open(os.path.join(COMPONENTS, name), encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)


# ---------------------------------------------------------------------------
# UX-15: Local security says what leaves, and when, instead of "never"
# ---------------------------------------------------------------------------

def test_local_security_makes_no_absolute_never_leaves_claim():
    """
    It read "YOUR DRAFTS, LEADS AND LINKEDIN SESSION NEVER LEAVE THIS MACHINE",
    while Send to LinkedIn sends the draft with that session, and a connected
    AI provider receives draft text.
    """
    rendered = _rendered("BrandStudioSurface.tsx")
    assert not re.search(r"never\s+leaves?\s+this\s+machine", rendered, flags=re.IGNORECASE), (
        "Local security promises something never leaves, which Send to LinkedIn and an AI provider contradict"
    )


def test_local_security_names_each_action_that_sends_and_what_it_sends():
    rendered = _rendered("BrandStudioSurface.tsx")
    for action, what in (
        ("Send to LinkedIn", "LinkedIn session"),
        ("AI provider", "draft"),
        ("Generate", "image description"),
    ):
        assert action in rendered, f"Local security does not say that {action} sends anything"
        assert what in rendered, f"Local security does not say what {action} sends"
