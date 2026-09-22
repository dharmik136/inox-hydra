"""
Engager dedupe: a person can engage with more than one post.
============================================================

The defect: the dedupe key was identity alone, and the Set holding it is module
level and never clears across LinkedIn's in-app navigation. So the first post a
creator opened claimed every commenter on it, and those same people were
silently filtered out of every later post in the session. They counted as
already known rather than as skipped, so no toast fired and nothing reported a
dropped capture.

Per-post attribution is the feature this extension exists to feed, and this was
losing exactly the rows that feed it.

These execute the real function out of content.js under node rather than
grepping for its shape, because the shape is not the thing that was wrong.
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


def _dedupe_keys(cases):
    """
    Runs engagerDedupeKey from content.js against a list of cases.

    Each case is [profileUrl, name, headline, postUrn, pathname]. Returns the
    resulting keys in order.
    """
    source = open(CONTENT_JS, encoding="utf-8").read()
    match = re.search(r"function engagerDedupeKey[\s\S]*?\n}", source)
    assert match, "engagerDedupeKey is not defined in content.js"

    script = (
        "global.window = { location: { pathname: '/feed/' } };\n"
        + match.group(0)
        + "\nconst cases = " + json.dumps(cases) + ";\n"
        + "const out = cases.map(c => { window.location.pathname = c[4];"
          " return engagerDedupeKey(c[0], c[1], c[2], c[3]); });\n"
        + "process.stdout.write(JSON.stringify(out));"
    )

    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, "node failed:\n" + result.stderr
    return json.loads(result.stdout)


ALICE = "https://www.linkedin.com/in/alice-probe"
TUESDAY = "urn:li:activity:111"
THURSDAY = "urn:li:activity:222"


def test_one_person_is_captured_on_every_post_they_engaged_with():
    """
    The exact scenario: a creator opens Tuesday's post, then clicks through to
    Thursday's without a reload. Alice commented on both.
    """
    keys = _dedupe_keys([
        [ALICE, "Alice", "VP Eng", TUESDAY, "/feed/"],
        [ALICE, "Alice", "VP Eng", THURSDAY, "/feed/"],
    ])
    assert keys[0] != keys[1], (
        "the same person on two different posts produced one key, so the "
        "second post's capture is silently dropped"
    )


def test_the_same_person_on_the_same_post_is_still_deduped():
    """Scrolling back up a comment list must not create duplicate rows."""
    keys = _dedupe_keys([
        [ALICE, "Alice", "VP Eng", TUESDAY, "/feed/"],
        [ALICE, "Alice", "VP Eng", TUESDAY, "/feed/"],
    ])
    assert keys[0] == keys[1], "re-reading the same card produced a second key"


def test_two_people_on_one_post_are_distinct():
    keys = _dedupe_keys([
        [ALICE, "Alice", "VP Eng", TUESDAY, "/feed/"],
        ["https://www.linkedin.com/in/bob-probe", "Bob", "CTO", TUESDAY, "/feed/"],
    ])
    assert keys[0] != keys[1]


def test_without_a_urn_two_post_pages_still_separate():
    """
    postUrnFor cannot always read a URN off the card. Falling back to identity
    alone would reinstate the bug for that subset, so the page path stands in.
    """
    keys = _dedupe_keys([
        [ALICE, "Alice", "VP Eng", None, "/posts/one"],
        [ALICE, "Alice", "VP Eng", None, "/posts/two"],
    ])
    assert keys[0] != keys[1], (
        "with no URN available, two different post pages produced one key"
    )


def test_a_person_with_no_profile_url_still_scopes_by_post():
    """Identity falls back to name and headline; the scope must still apply."""
    keys = _dedupe_keys([
        ["", "Alice", "VP Eng", TUESDAY, "/feed/"],
        ["", "Alice", "VP Eng", THURSDAY, "/feed/"],
    ])
    assert keys[0] != keys[1]


def test_the_page_path_is_never_stored_as_a_post_urn():
    """
    The path is a dedupe scope, not an identifier. Writing it into post_urn
    would put a value this extension invented into LinkedIn's namespace, which
    is the mistake commit 3c80f4b was written to undo elsewhere.
    """
    source = open(CONTENT_JS, encoding="utf-8").read()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("post_urn:"):
            assert "pathname" not in stripped, (
                "post_urn is being filled from the page path: " + stripped
            )
