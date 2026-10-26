"""
Patterns compares each form once, in words a creator reads.
==========================================================

Cycle 2, batch R5, D-13. The same seven forms were compared twice on one
screen: "EACH SIDE NEEDS 3" in the first list, then "Binary feature
comparisons" with "ABSTAIN (N < 8)" and "NEEDS AT LEAST 8 PER ARM". The topic
sentence read "Your Other posts posts". Posts by month was a row of bars with
no scale.
"""

from qc2_r5_live import ME, confirm_identity, server, studio, urn_days_ago  # noqa: F401


def _posts(client, count):
    posts = []
    for index in range(count):
        opening = f"Why does dispatch slip on day {index}?" if index % 2 else f"Dispatch notes, day {index}."
        posts.append({"activity_urn": urn_days_ago(10 + index * 3, index), "actor": ME,
                      "text": opening + "\n\nThe detail.", "reactions": 20 + index * 2, "comments": 1})
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": posts}).status_code == 200


def test_each_form_is_compared_once_without_statistics_words(studio):
    client = studio["client"]
    confirm_identity(client)
    # Eight posts a side, which is what both lists now ask for (batch T2:
    # this screen published at three while the Evidence panel suppressed the
    # same split at eight).
    _posts(client, 18)
    page = studio["page"]
    page.goto(studio["url"] + "/#/patterns", wait_until="networkidle")
    page.wait_for_selector("text=Went with more or fewer reactions")
    body = page.inner_text("main")
    for jargon in ("Binary feature comparisons", "Feature Contrasts", "ABSTAIN", "PER ARM"):
        assert jargon not in body, f"{jargon!r} is still on the screen"
    assert body.count("An opening line that asks a question") == 1, body
    assert "Each side needs 8 posts before a line is shown" in body, body
    assert "Settled means" in body, body
    # Posts by month, with its scale in words, moved to the Queue with the
    # rest of the rhythm in cycle 4 (tests/test_qc4_t3_cadence_moved_to_queue.py).
    assert "THE TALLEST BAR IS" not in body, body


def test_the_help_describes_one_list():
    """
    Cycle 4 drew the one list from the contrast engine's records and retired
    the EARLY tag, which could not fire (tests/test_qc4_t3_patterns_from_the_engine.py),
    so the help names neither the old second list nor the tag.
    """
    import os

    path = os.path.join(os.path.dirname(__file__), "..", "docs", "help", "see-what-worked-and-where-your-attention-goes.md")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    assert "Feature Contrasts" not in text and "**EARLY**" not in text
    assert "Evidence panel" in text, "the help no longer says the lines are the Evidence panel's"


def test_the_topic_sentence_names_other_posts_once():
    import evidence_briefing

    assert evidence_briefing._topic_posts("Other posts") == "Other posts"
    assert evidence_briefing._topic_posts("Croissant") == "Croissant posts"


def test_the_topic_sentence_on_screen(studio):
    client = studio["client"]
    confirm_identity(client)
    _posts(client, 6)
    page = studio["page"]
    page.goto(studio["url"] + "/#/patterns", wait_until="networkidle")
    page.wait_for_selector("text=Topic to Qualified Lead Attribution")
    assert "posts posts" not in page.inner_text("main")
