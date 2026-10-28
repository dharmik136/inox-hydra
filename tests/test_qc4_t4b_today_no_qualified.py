"""
Today's "What worked" names no qualified leads.
================================================

Decision 7 of the sections report retired the "qualified" framing: who is
qualified rests on the ICP tier, a guess, and a per-post count of qualified
people breaks the single-reading rule. Patterns and Audience dropped it in
cycle 4 (track 3, M4; track 4, Audience). Today's "What worked" still put
"N qualified leads" under each of the strongest and weakest posts.

Strict Invariants:
- Zero em-dashes.
"""

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TODAY = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TodaySurface.tsx")


def _what_worked():
    """The panel's code without its comments, which may say why the count is gone."""
    with open(TODAY, encoding="utf-8") as handle:
        source = handle.read()
    panel = source.split("function WhatWorked")[1].split("\n}\n")[0]
    panel = re.sub(r"/\*.*?\*/", "", panel, flags=re.S)
    return "\n".join(line.split("//")[0] for line in panel.splitlines())


def test_what_worked_counts_no_qualified_leads():
    panel = _what_worked()
    assert "qualified" not in panel.lower(), "Today's What worked still counts qualified leads"


def test_what_worked_still_says_what_each_post_drew():
    panel = _what_worked()
    assert re.search(r"count\(item\.reactions\)\}\s*reactions", panel)
    assert "comments" in panel
