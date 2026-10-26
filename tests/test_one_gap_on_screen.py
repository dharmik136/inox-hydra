"""
Today and the Queue say the same thing about the creator's rhythm.
==================================================================

tests/test_one_gap_format.py reads the tree and holds that no screen formats a
gap itself. This drives the built interface and reads the number off both
screens, because a static guard cannot show that two screens agree: they could
both call the one formatter and still be handed different measurements.

Before this, Today printed `USUAL GAP 0.9 DAYS` and Patterns printed
`Usual gap 1 days` about the same posts.

Cycle 4 moved the rhythm from Patterns to the Queue, where the week lives, so
the second screen read here is the Queue.
"""

import re

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import (  # noqa: F401
    ME,
    confirm_identity,
    open_section,
    seed_creator,
    server,
    studio,
    urn_days_ago,
)

# The one wording, read from the module the screens import it from.
NOT_MEASURED = "Not measured"

# An integer is matched too, so a screen that rounded reports the
# disagreement ("0.9 against 1") rather than "nothing printed".
DAYS = re.compile(r"(\d+(?:\.\d+)?)\s+days", re.I)


def _number_after(page, label):
    """The figure printed beside `label`, whatever element holds it."""
    text = page.locator("main").inner_text()
    index = text.lower().index(label.lower())
    found = DAYS.search(text[index : index + 90])
    assert found, f"no gap in days printed after {label!r}: {text[index:index + 90]!r}"
    return found.group(1)


def test_today_and_the_queue_print_the_same_usual_gap(studio):
    seed_creator(studio["client"])

    page = open_section(studio, "today")
    expect(page.locator("h1")).to_have_text("What to do in the next hour")
    today_gap = _number_after(page, "usual gap")

    page = open_section(studio, "queue")
    expect(page.locator("main")).to_contain_text("Against your own rhythm", timeout=10000)
    queue_gap = _number_after(page, "usual gap")

    assert today_gap == queue_gap, (
        f"Today says the usual gap is {today_gap} days and the Queue says "
        f"{queue_gap} days, about the same posts"
    )
    # One decimal, on both, which is the precision the backend measured.
    assert "." in today_gap, f"Today rounded the gap away: {today_gap}"


def test_one_post_has_no_gap_to_measure_and_both_screens_say_so_the_same_way(studio):
    """
    A creator with one post has no gap between posts, so the backend sends no
    median_gap_days. Today said "USUAL GAP NOT MEASURED" and Patterns said
    "Unknown": one state, two words. The rhythm is on the Queue now. (Patterns' `?? 0` default was not
    reachable, because the screen returns early when no posts have been read.)
    """
    client = studio["client"]
    confirm_identity(client)
    ingested = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn_days_ago(3, 0), "actor": ME,
         "text": "One post, and nothing to measure a gap against.\n\nIts body.",
         "reactions": 12, "comments": 1, "reposts": 0},
    ]})
    assert ingested.status_code == 200, ingested.text

    page = open_section(studio, "queue")
    expect(page.locator("main")).to_contain_text("Against your own rhythm", timeout=10000)
    queue = page.locator("main").inner_text()
    assert "Unknown" not in queue, "the Queue has its own word for an unmeasured gap"
    assert NOT_MEASURED in queue, f"the Queue does not say the gap is unmeasured: {queue[:200]!r}"

    page = open_section(studio, "today")
    expect(page.locator("h1")).to_have_text("What to do in the next hour")
    today = page.locator("main").inner_text()
    assert NOT_MEASURED.upper() in today.upper(), (
        f"Today does not say the gap is unmeasured: {today[:200]!r}"
    )
