"""
The help sends a creator to Posts for their posts, not to Analytics.
===================================================================

Review round 2, B2 (c). Analytics' post table moved to Posts in batch 1, and
five sentences in four articles still said a published post appears in, is
listed in, or stays in Analytics. The find-a-post table said Posts holds the
published posts while a post sent to LinkedIn and not yet read back was on
no list; it is now under Posts' table, and the table says so. The Queue
article's drafts sentence promised the 12-hour rule, which the next-slot
route keeps only when a slot can (review N9).
"""

import os
import re

HELP = os.path.join(os.path.dirname(__file__), "..", "docs", "help")


def _article(name):
    with open(os.path.join(HELP, name), encoding="utf-8") as handle:
        return handle.read()


def _articles():
    for name in sorted(os.listdir(HELP)):
        if name.endswith(".md"):
            yield name, _article(name)


PLACES_A_POST_IN_ANALYTICS = re.compile(
    r"(published|post)[^.\n]{0,60}\b(in|appears in|appear in|listed in|stays in)\s+\*\*Analytics\*\*")


def test_no_article_places_a_post_in_analytics():
    found = []
    for name, text in _articles():
        for number, line in enumerate(text.splitlines(), 1):
            if PLACES_A_POST_IN_ANALYTICS.search(line):
                found.append(f"{name}:{number}")
    assert not found, f"these lines still place a post in Analytics, which lists none since cycle 4: {found}"


def test_the_find_a_post_table_names_both_places_on_posts():
    row = next(line for line in _article("start-a-new-post-or-find-an-earlier-one.md").splitlines()
               if line.startswith("| **Posts**"))
    assert "not yet seen on LinkedIn" in row, row


def test_the_queue_article_does_not_promise_the_12_hour_rule_for_every_slot():
    text = " ".join(_article("how-the-queue-works.md").split())
    assert "puts that one in the next slot clear of the 12-hour rule" not in text
    assert "24 hours ahead" in text
