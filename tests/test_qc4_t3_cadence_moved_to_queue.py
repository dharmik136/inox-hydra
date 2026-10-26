"""
How steadily the creator posts lives on the Queue, once.
========================================================

Patterns carried a "Cadence" block (posts, since the last, the usual gap,
queued in the next 14 days, the longest gap, posts by month, posts by
weekday) that was a second rendering of the same insights.cadence_overview
payload the Queue prints as "Against your own rhythm" (cycle 4, track 3,
batch 1, from the sections report: three sections did another section's
job). The week lives on the Queue, so the rhythm moved there; Patterns keeps
its one job, what the creator's own posts suggest, and no longer fetches the
cadence payload at all.
"""

import os

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401,E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")


def _read(name):
    with open(os.path.join(COMPONENTS, name), encoding="utf-8") as handle:
        return handle.read()


def test_patterns_no_longer_reads_the_cadence_payload():
    source = _read("PatternsSurface.tsx")
    assert "fetchCadenceInsights" not in source, "Patterns still fetches the rhythm the Queue shows"
    assert "MonthStrip" not in source and "POSTS BY WEEKDAY" not in source


def test_the_queue_carries_every_part_of_the_block_that_moved():
    source = _read("QueueSurface.tsx")
    for part in ('label="Longest gap"', 'label="Next 14 days"', "function MonthStrip", "POSTS BY WEEKDAY",
                 "No best day is named"):
        assert part in source, f"the Queue lost {part!r} in the move"


def test_the_rhythm_is_on_the_queue_and_not_on_patterns(studio):
    seed_creator(studio["client"])
    page = open_section(studio, "queue")
    rhythm = page.locator("section[aria-labelledby=queue-cadence]")
    expect(rhythm).to_contain_text("Against your own rhythm", timeout=10000)
    for words in ("Longest gap", "Next 14 days", "THE TALLEST BAR IS", "POSTS BY WEEKDAY", "No best day is named"):
        expect(rhythm).to_contain_text(words)
    assert studio["errors"] == [], studio["errors"]

    page = open_section(studio, "patterns")
    expect(page.locator("h1")).to_have_text("What your own posts suggest", timeout=10000)
    body = page.locator("main").inner_text()
    for words in ("POSTS BY WEEKDAY", "THE TALLEST BAR IS", "Usual gap", "Since last post"):
        assert words not in body, f"Patterns still draws {words!r}, which is the Queue's"
    assert studio["errors"] == [], studio["errors"]
