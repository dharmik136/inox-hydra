"""
A pattern with no ratio is said to have none, not "not enough posts".
=====================================================================

results.difference answers "not_measured" when both sides have enough posts
but the ratio could not be computed: the posts without the form have a
median of 0 reactions, so there is nothing to divide by. The Patterns screen
let such a line into its main list and, opened, worded it "not enough posts
to say", which is the wording for a different verdict, "too_few_posts"
(cycle 4, track 3, batch 0, from the sections report's defects table). The
screen now names each verdict in its own words and keeps the unmeasured line
out of the list of findings.
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import results  # noqa: E402

SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PatternsSurface.tsx")


def test_the_engine_tells_the_two_verdicts_apart():
    assert results.difference(None, 2, 20)["verdict"] == "too_few_posts"
    assert results.difference(None, 20, 20)["verdict"] == "not_measured"


def test_the_screen_words_each_verdict_in_its_own_words():
    with open(SURFACE, encoding="utf-8") as handle:
        source = handle.read()
    words = source[source.index("function verdictWord"):]
    words = words[:words.index("\n}") + 2]
    assert 'case "too_few_posts"' in words, "the too-few verdict has no wording of its own"
    assert 'case "not_measured"' in words, "a line with no ratio is still worded as not enough posts"
    assert "default:" not in words or "not enough posts to say" not in words.split("default:", 1)[1], (
        "the default wording still claims not enough posts for any verdict it does not know"
    )


def test_an_unmeasured_line_is_kept_out_of_the_findings():
    with open(SURFACE, encoding="utf-8") as handle:
        source = handle.read()
    assert re.search(r'verdict\(\w+\) === "not_measured"', source), "no bucket holds the unmeasured lines"
    assert "NO RATIO CAN BE MEASURED" in source, "the screen does not say which forms have no ratio"
