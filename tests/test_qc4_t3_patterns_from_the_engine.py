"""
Patterns draws its comparisons from the contrast engine's records.
=================================================================

Patterns fetched /api/v1/insights/contrasts and read only each record's
status and key, to build an EARLY tag that could not fire: the screen's own
lines came from a second payload computing the same comparison with the
same minimum a side (cycle 4, track 3, batch 1, from the sections report:
"Patterns' contrasts wired from the payload it already fetches"). The lines
are now the engine's records: its medians, its ratio, its counts per side,
its abstention below the minimum, "no difference" as a list of its own, and
its period guard. They are the records the Composer's Evidence panel is
built from, so the two screens cannot disagree about a line.

The browser test plants a contrasts payload the patterns payload could not
produce and reads it back off the screen, which only a screen drawing from
the engine's records can pass.
"""

import json
import os

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401,E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PatternsSurface.tsx")


def _difference(verdict, n_with, n_without, ratio=None):
    return {"verdict": verdict, "notable": verdict in ("more", "fewer"), "ratio": ratio,
            "n_with": n_with, "n_without": n_without, "min_per_side": 8}


PLANTED = {
    "status": "success",
    "settled_posts_count": 23,
    "settled_after": {"hours": 168, "measured": False, "posts": 0},
    "min_arm_size": 8,
    "contrasts": [
        {"key": "hashtags", "label": "Hashtags", "status": "conclusive", "n_with": 11, "n_without": 12,
         "median_with": 77, "median_without": 33, "ratio": 2.33, "planted_or_significant": True,
         "difference": _difference("more", 11, 12, 2.33), "min_required": 8},
        {"key": "question_opening", "label": "An opening line that asks a question", "status": "conclusive",
         "n_with": 10, "n_without": 13, "median_with": 41, "median_without": 39, "ratio": 1.05,
         "planted_or_significant": False, "difference": _difference("none", 10, 13, 1.05), "min_required": 8},
        {"key": "symbol_opening", "label": "An opening that starts with an emoji or symbol",
         "status": "different_period", "n_with": 9, "n_without": 14, "median_with": 60, "median_without": 30,
         "ratio": 2.0, "planted_or_significant": False, "different_period": True,
         "typical_year_with": 2023, "typical_year_without": 2026,
         "difference": {**_difference("more", 9, 14, 2.0), "verdict": "different_period", "notable": False},
         "min_required": 8},
        {"key": "long_post", "label": "More than 1,500 characters", "status": "not_enough_data",
         "n_with": 2, "n_without": 21, "difference": _difference("too_few_posts", 2, 21), "min_required": 8,
         "confidence": "insufficient_sample"},
    ],
}


def test_the_screen_reads_the_engines_records_and_nothing_else_for_its_lines():
    with open(SURFACE, encoding="utf-8") as handle:
        source = handle.read()
    assert "contrasts?.contrasts" in source
    for second_copy in ("patterns.patterns", "patterns.not_enough_posts", "early.has(", "EARLY\""):
        assert second_copy not in source, f"the screen still reads {second_copy!r}"


def test_the_screen_shows_what_the_engine_answered(studio):
    seed_creator(studio["client"])
    page = studio["page"]
    page.route("**/api/v1/insights/contrasts",
               lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(PLANTED)))
    open_section(studio, "patterns")
    main = page.locator("main")
    expect(main).to_contain_text("Went with more or fewer reactions", timeout=10000)
    findings = page.locator("section", has_text="Went with more or fewer reactions").first
    expect(findings).to_contain_text("Hashtags")
    expect(findings).to_contain_text("MEDIAN 77 REACTIONS ON 11 POSTS WITH IT, 33 ON 12 WITHOUT")
    expect(findings).to_contain_text("2.3x")
    same = page.locator("section", has_text="No difference your own posts can separate").first
    expect(same).to_contain_text("An opening line that asks a question")
    expect(same).to_contain_text("MEDIAN 41 REACTIONS ON 10 POSTS WITH IT, 39 ON 13 WITHOUT")
    mixed = page.locator("section", has_text="Mixed up with when you posted").first
    expect(mixed).to_contain_text("MOSTLY 2023 AGAINST MOSTLY 2026")
    expect(main).to_contain_text("MORE THAN 1,500 CHARACTERS (2 WITH, 21 WITHOUT)")
    expect(main).to_contain_text("across your 23 posts whose figures have settled")
    assert "EARLY" not in main.inner_text()
    assert studio["errors"] == [], studio["errors"]


def test_a_comparison_that_could_not_be_read_is_not_an_empty_one(studio):
    seed_creator(studio["client"])
    page = studio["page"]
    page.route("**/api/v1/insights/contrasts", lambda route: route.fulfill(status=500, body="{}"))
    open_section(studio, "patterns")
    main = page.locator("main")
    expect(main).to_contain_text("THE COMPARISONS COULD NOT BE READ", timeout=10000)
    assert "NO FORM HAS ENOUGH POSTS" not in main.inner_text(), "a failed read is drawn as too few posts"
