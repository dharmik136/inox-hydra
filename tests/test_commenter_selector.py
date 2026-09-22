"""
The commenter name selector honours priority, not document order.
=================================================================

querySelector with a comma separated list returns the first element in
DOCUMENT order matching any selector. It does not try them in the order
written, so the order a developer puts them in carries no weight.

The commenter selector ended with a bare [aria-hidden="true"], and LinkedIn
puts that attribute on avatar wrappers, bullet separators and relative
timestamps, all of which sit before the name inside a comment card. Verified
against a card shaped like LinkedIn's:

    avatar div first     the old list returned "", the name failed the
                         length >= 2 guard, and the commenter was dropped
    timestamp first      the old list returned "2h", which passes the guard,
                         so a lead named "2h" entered the CRM with a real
                         profile URL attached

The reactions path two lines away already scoped it correctly, so the two
halves of the same feature disagreed.

These exercise firstNamedElement under node with a stub root, which tests the
priority logic without adding jsdom as a dependency.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONTENT_JS = os.path.join(REPO_ROOT, "studio", "extension", "content.js")

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required to execute the extension logic"
)


def _pick(dom_map, selectors):
    """
    Runs firstNamedElement against a stub root.

    dom_map maps a selector to the text its match would contain. A selector
    absent from the map matches nothing, which is what a real card does for
    the classes it does not carry.
    """
    source = open(CONTENT_JS, encoding="utf-8").read()
    match = re.search(r"function firstNamedElement[\s\S]*?\n\}", source)
    assert match, "firstNamedElement is not defined in content.js"

    script = (
        match.group(0)
        + "\nconst map = " + json.dumps(dom_map) + ";\n"
        + "const root = { querySelector: (s) => "
          "Object.prototype.hasOwnProperty.call(map, s) "
          "? { innerText: map[s], textContent: map[s] } : null };\n"
        + "const el = firstNamedElement(root, " + json.dumps(selectors) + ");\n"
        + "process.stdout.write(JSON.stringify(el ? el.innerText : null));"
    )

    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, "node failed:\n" + result.stderr
    return json.loads(result.stdout)


NAME_CLASS = ".comments-post-meta__name-text"
ARIA_SCOPED = '.comments-comment-item__profile-link span[aria-hidden="true"]'
PRIORITY = [NAME_CLASS, ARIA_SCOPED, ".update-components-actor__name"]


def test_the_highest_priority_selector_wins():
    """
    Even when a lower priority selector would also match. This is the property
    querySelector does not have and the whole reason the helper exists.
    """
    picked = _pick(
        {NAME_CLASS: "Priya Raman", ARIA_SCOPED: "2h"},
        PRIORITY,
    )
    assert picked == "Priya Raman", (
        "a lower priority selector won, which is how a timestamp became a lead"
    )


def test_it_falls_through_when_the_preferred_selector_is_absent():
    picked = _pick({ARIA_SCOPED: "Priya Raman"}, PRIORITY)
    assert picked == "Priya Raman"


def test_an_empty_match_does_not_stop_the_search():
    """
    The avatar case. A matching element carrying no text must not end the
    search, or the card is dropped even though the name is right there.
    """
    picked = _pick({NAME_CLASS: "", ARIA_SCOPED: "Priya Raman"}, PRIORITY)
    assert picked == "Priya Raman", (
        "an empty first match ended the search and the commenter was lost"
    )


def test_nothing_matching_returns_nothing():
    assert _pick({}, PRIORITY) is None


def test_a_single_character_is_not_a_name():
    """The length guard lives in the helper so every call site inherits it."""
    picked = _pick({NAME_CLASS: "P", ARIA_SCOPED: "Priya Raman"}, PRIORITY)
    assert picked == "Priya Raman"


def test_no_bare_aria_hidden_selector_survives():
    """
    Structural, and the thing that actually regressed. A bare
    [aria-hidden="true"] in a selector list matches avatars, separators and
    timestamps anywhere in the card.
    """
    source = open(CONTENT_JS, encoding="utf-8").read()

    offenders = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("*") or stripped.startswith("//"):
            continue
        # A bare attribute selector, not one qualified by an element or class.
        if re.search(r"(?<![\w\]\)])\[aria-hidden=[\"']true[\"']\]", stripped):
            offenders.append(str(number) + ": " + stripped[:90])

    assert not offenders, (
        "an unqualified [aria-hidden] selector is back:\n  " + "\n  ".join(offenders)
    )


def test_both_capture_paths_use_the_helper():
    """
    The comment path and the reaction path are two halves of one feature and
    previously disagreed about this.
    """
    source = open(CONTENT_JS, encoding="utf-8").read()
    assert source.count("firstNamedElement(") >= 3, (
        "expected the helper definition plus both call sites"
    )
