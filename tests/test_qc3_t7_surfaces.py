"""
Three screens that now fit, and an export a creator can find.
=============================================================

Cycle 3, batch T7, against the built interface (tests/qc2_r5_live.py).

  Activity      18.2% ink, 13,669 characters, 6.1 scroll pages: five tabs of
                fifty cards each, read from one 56 KB answer. Now one log,
                newest first, grouped by day, one line each, filtered by kind.
  Outbound      5.1% ink, 321 characters, one control on an install holding
                44,000 rows. Now the people, the figures and the three lists
                reciprocity actually answers, across the window.
  Brand Studio  Export sat at y=1322 under "Local security" while a tab named
                "Storage and privacy" existed beside it (ONEVIEW section 2).
                Your data is now the first thing in that tab.
  Leads         the dossier's identity fields were two columns at every
                width, about 150 pixels each on a phone, and the dossier
                capped itself at 70 characters in a pane twice that wide. It
                now also groups a person's engagement with the creator's own
                posts, which is drawn here because it is drawn in the browser.

The scroll page and ink numbers of the section bar are measured on the three
year dataset, not here; these hold the shape that makes them possible, on a
seeded install, at the 1440x900 the bar is set at.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from qc2_r5_live import ME, open_section, seed_creator, server, studio, urn_days_ago  # noqa: F401,E402


def _pages(page):
    """The screen's height in viewports, which is what "scroll pages" means."""
    return page.evaluate(
        "() => {const m = document.querySelector('main') || document.body;"
        " return m.scrollHeight / window.innerHeight;}"
    )


# ---------------------------------------------------------------------------
# Activity: a log that fits
# ---------------------------------------------------------------------------

def _seed_activity(client, posts=20, comments=20, reactions=20):
    seed_creator(client)
    extra = [{"activity_urn": urn_days_ago(3 + i, 500 + i), "actor": ME,
              "text": f"An extra post number {i} with a sentence of detail after it.",
              "reactions": 10 + i, "comments": 1}
             for i in range(posts)]
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": extra}).status_code == 200
    items = [{"target_activity_urn": urn_days_ago(2 + i, 900 + i), "kind": "comment",
              "my_text": f"A comment of mine, number {i}, with enough words in it to wrap a card.",
              "target_author": f"Author {i}", "target_excerpt": "Their post, at some length, about logistics."}
             for i in range(comments)]
    items += [{"target_activity_urn": urn_days_ago(2 + i, 1900 + i), "kind": "reaction",
               "reaction_kind": "like", "target_author": f"Reactee {i}",
               "target_excerpt": "Another post of theirs about freight and queues."}
              for i in range(reactions)]
    assert client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": items}).status_code == 200


def test_activity_is_one_log_of_one_screenful_not_five_tabs_of_cards(studio):
    client, page = studio["client"], studio["page"]
    _seed_activity(client)
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")

    pages = _pages(page)
    assert pages <= 2.0, f"Activity is {pages:.1f} scroll pages, and the bar is 2"

    # One line per thing read, not a card: 60 things were seeded, and the log
    # draws the newest 24 of them with the count said on screen.
    lines = page.locator("main li").count()
    assert lines == 24, f"the log drew {lines} lines"
    assert "OF" in page.inner_text("main").upper()

    # The five tabs are gone, and the kinds are filters over one list.
    text = page.inner_text("main")
    assert "Outbound Comments (" not in text, text[:400]
    for label in ("Everything (", "Your posts (", "People ("):
        assert label in text, f"{label} is not offered as a filter"


def test_a_kind_filter_narrows_the_log_without_another_read(studio):
    client, page = studio["client"], studio["page"]
    _seed_activity(client, posts=6, comments=6, reactions=6)
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")
    page.get_by_role("button", name="Auto refresh on").click()

    reads = []
    page.on("request", lambda request: "/api/v1/self/activity-stream" in request.url and reads.append(request.url))
    page.get_by_role("button", name="Your reactions (6)").click()
    page.wait_for_timeout(250)
    assert reads == [], f"filtering read the stream again: {reads}"
    assert page.locator("main li").count() == 6


def test_activity_still_says_what_it_measured_and_what_it_did_not(studio):
    """A missing count reads "not measured" here as it does on Posts."""
    client, page = studio["client"], studio["page"]
    seed_creator(client, commenter=None)
    urn = urn_days_ago(4, 77)
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": "Nobody reads your roadmap.", "reactions": 4100}]}
    ).status_code == 200
    open_section(studio, "activity")
    page.wait_for_selector("text=Nobody reads your roadmap.")
    text = page.inner_text("main")
    assert "Reactions: 4,100" in text, text[:400]
    assert "Comments: not measured" in text, text[:400]


# ---------------------------------------------------------------------------
# Leads: the dossier at a phone's width, and a person's engagement history
# ---------------------------------------------------------------------------

def _open_dossier(studio, name):
    """The stream, with this person's dossier open, as a creator opens it."""
    page = studio["page"]
    open_section(studio, "leads")
    page.wait_for_selector("text=Lead stream")
    row = page.get_by_role("button", name=name, exact=False).first
    row.wait_for()
    row.click()
    # The dossier is an article, and at a phone's width it replaces the
    # stream rather than sitting beside it, so the person's name appears in
    # two places of which one is hidden. The article is the pane itself.
    page.locator("main article").first.wait_for(state="visible")
    page.wait_for_selector("main dl")
    return page


@pytest.mark.parametrize("width,height,columns", [(1440, 900, 2), (390, 844, 1)])
def test_the_dossier_fields_are_one_column_on_a_phone(studio, width, height, columns):
    """
    Company, seniority, the score and the first-seen date were a fixed two
    column grid: at 390 wide each column was about 150 pixels and a company
    name or a score with its tier was squeezed into it.
    """
    client, page = studio["client"], studio["page"]
    seed_creator(client, commenter="Anika Shah")
    page.set_viewport_size({"width": width, "height": height})
    _open_dossier(studio, "Anika Shah")

    tracks = page.evaluate(
        "() => {const dl = document.querySelector('main dl');"
        " return dl ? getComputedStyle(dl).gridTemplateColumns.split(' ').length : 0;}"
    )
    assert tracks == columns, f"the dossier's fields are {tracks} columns at {width} wide"

    overflow = page.evaluate(
        "() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)")
    assert overflow == 0, f"{overflow}px of horizontal overflow at {width} wide"
    widest = page.evaluate(
        "() => Math.max(0, ...Array.from(document.querySelectorAll('main *'))"
        ".map((el) => el.getBoundingClientRect().right)) - window.innerWidth")
    assert widest <= 1, f"an element reaches {widest:.0f}px past the window at {width} wide"


def test_the_dossier_groups_what_a_person_did_on_each_of_your_posts(studio):
    """
    One row per post of the creator's, from the whole history rather than the
    handful of interactions the timeline lists: two comments and a reaction on
    one post is one row saying so.
    """
    client = studio["client"]
    urns = seed_creator(client, commenter=None)
    for interaction, comment, urn in (
        ("COMMENT", "First thought on this one.", urns[0]),
        ("COMMENT", "And a second, later.", urns[0]),
        ("LIKE", None, urns[0]),
        ("LIKE", None, urns[1]),
    ):
        answer = client.post("/api/v1/crm/interactions/ingest", json={
            "full_name": "Nadia Okonkwo", "profile_url": "https://www.linkedin.com/in/nadia-okonkwo-x",
            "headline": "Head of Operations at Harbourline", "company": "Harbourline",
            "interaction_type": interaction, "comment_text": comment,
            "post_urn": urn, "post_author": ME,
        })
        assert answer.status_code == 200, answer.text

    page = _open_dossier(studio, "Nadia Okonkwo")
    page.wait_for_selector("text=Engagement with your posts")
    section = page.locator("main section").filter(has_text="Engagement with your posts").first
    rows = section.locator("li")
    assert rows.count() == 2, f"{rows.count()} posts listed for two posts engaged with"
    text = section.inner_text()
    assert "2 comments, 1 reaction" in text, text
    assert "1 reaction" in text, text
    # Each row names the post, so the creator does not have to remember which.
    assert "on-call rota" in text, text


# ---------------------------------------------------------------------------
# Outbound: rebuilt on what the live capture path records
# ---------------------------------------------------------------------------

def test_outbound_shows_the_people_the_figures_and_the_three_lists(studio):
    client, page = studio["client"], studio["page"]
    urns = seed_creator(client, commenter="Anika Shah", comment="This matches what we saw last year.")
    items = [{"target_activity_urn": urn_days_ago(5 + i, 300 + i), "kind": "reaction",
              "reaction_kind": "like", "target_author": "Anika Shah"} for i in range(3)]
    items += [{"target_activity_urn": urn_days_ago(5 + i, 400 + i), "kind": "comment",
               "my_text": f"A reply of mine number {i}.", "target_author": f"Stranger {i}"}
              for i in range(4)]
    assert client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": items}).status_code == 200
    assert urns

    open_section(studio, "outbound")
    page.wait_for_selector("text=Where your attention goes")
    text = page.inner_text("main")

    # The section labels are drawn uppercase by studio-label, so they are
    # compared that way rather than as written in the source.
    for heading in ("ENGAGED BACK", "GONE QUIET", "ONE-WAY", "MOST ENGAGED WITH"):
        assert heading in text.upper(), f"Outbound does not answer {heading!r}: {text[:400]}"
    assert "Anika Shah" in text
    # The figures are counted, and the table says when each side last acted.
    for column in ("LAST FROM THEM", "LAST FROM YOU", "ON YOUR POSTS"):
        assert column in text.upper(), column
    pages = _pages(page)
    assert pages <= 2.0, f"Outbound is {pages:.1f} scroll pages"

    # It used 34% of the width it was given. The table alone now spans more.
    width = page.evaluate(
        "() => {const t = document.querySelector('main table');"
        " return t ? t.getBoundingClientRect().width : 0;}"
    )
    assert width > 700, f"the table is {width:.0f}px wide in a 1384px work area"


def test_outbound_does_not_call_an_account_quiet_before_it_has_looked(studio):
    """The same coverage rule as one-way, said on screen rather than guessed."""
    client, page = studio["client"], studio["page"]
    from qc2_r5_live import confirm_identity

    confirm_identity(client)
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn_days_ago(30, 11), "actor": ME, "text": "A post nobody has been read on.",
         "reactions": 12, "comments": 2}]}).status_code == 200
    assert client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": urn_days_ago(4, i), "kind": "reaction", "target_author": "Frequent Author"}
        for i in range(4)]}).status_code == 200

    open_section(studio, "outbound")
    page.wait_for_selector("text=Where your attention goes")
    text = page.inner_text("main").upper()
    assert "NOT JUDGED YET" in text, text[:500]
    assert "FREQUENT AUTHOR" in text, "the account is still ranked, only not judged"


# ---------------------------------------------------------------------------
# The folded instruction box: no less available than the section it replaced
# ---------------------------------------------------------------------------

def _open_prompt(studio):
    page = studio["page"]
    open_section(studio, "composer")
    opener = page.locator('button[aria-label="Open inspector"]')
    if opener.count() and opener.is_visible():
        opener.click()
    page.click('aside[aria-label="Inspector"] button:has-text("Prompt")')
    return page


def test_an_instruction_still_runs_when_the_engine_status_cannot_be_read(studio):
    """
    The Command section omitted its banner when /api/ai/status failed and kept
    the form working. Folded into the Prompt panel, a failed status replaced
    the whole panel, so the capability became less available than before.
    """
    client, page = studio["client"], studio["page"]
    seed_creator(client, commenter=None)
    page.route("**/api/ai/status", lambda route: route.fulfill(status=503, body="{}"))

    _open_prompt(studio)
    page.wait_for_selector("#agent-command")
    text = page.inner_text('aside[aria-label="Inspector"]').upper()
    assert "ENGINE STATUS UNAVAILABLE" in text, text[:300]
    assert page.locator('button[aria-label="Run the command"]').count() == 1
    assert not studio["errors"], studio["errors"]


# ---------------------------------------------------------------------------
# Brand Studio: export where a creator looks for it
# ---------------------------------------------------------------------------

def test_your_data_is_the_first_thing_in_storage_and_privacy(studio):
    page = studio["page"]
    seed_creator(studio["client"], commenter=None)
    open_section(studio, "settings")
    page.get_by_role("tab", name="Storage and privacy").click()
    page.wait_for_selector("text=Export JSON")

    box = page.get_by_text("Export JSON").first.bounding_box()
    assert box is not None
    assert box["y"] < 900, f"Export JSON is at y={box['y']:.0f} in a 900 pixel window"


def test_local_security_no_longer_hides_the_export(studio):
    page = studio["page"]
    seed_creator(studio["client"], commenter=None)
    open_section(studio, "settings")
    page.get_by_role("tab", name="Local security").click()
    page.wait_for_selector("text=This install processes your work on this machine.")
    text = page.inner_text("main")
    assert "Export JSON" not in text, "Export is still under Local security"
    assert "Export CSV" not in text
