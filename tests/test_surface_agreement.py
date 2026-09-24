"""
Surface Agreement Guards
========================
Two defects found by driving the running studio rather than by building it or
running the suite. Neither was visible from a diff, both rendered cleanly, and
both put something false or meaningless in front of a reader.

1. The lead stream card announced COMMENTED while the dossier for that same
   lead, on the same screen, said NO INTERACTIONS RECORDED. The card reads
   leads.engagement_type; the dossier read only the lead_interactions table,
   and the engagement that captures a lead is written to the first and not the
   second. The studio was stating two different things about one person.

2. Every card on the swipe wall read "CONTRARIAN TRUTHS . CONTRARIAN TRUTHS",
   because archetype and topic hold the same value for all 36 seeded
   specimens and the card printed both with a separator between them.

Each test here has two halves: the backend condition that produces the defect,
asserted against real data so the guard cannot quietly stop applying, and the
component's handling of it. The first half is what keeps the second honest.
"""

import os
import re

import pytest
from fastapi.testclient import TestClient

from app import app
from database import init_db

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
LEADS_SURFACE = os.path.join(COMPONENTS, "LeadsSurface.tsx")
SWIPE_SURFACE = os.path.join(COMPONENTS, "SwipeSurface.tsx")

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def ensure_db():
    init_db()


def _source(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# 1. The lead dossier and the lead card describe the same person
# ---------------------------------------------------------------------------


def test_a_captured_engagement_lives_on_the_lead_not_the_timeline():
    """
    Establishes the condition, so the guard below cannot pass vacuously.

    If this starts failing, the backend began writing capture engagements into
    lead_interactions and the dossier's fallback is no longer load bearing.
    """
    listed = client.get("/api/leads")
    assert listed.status_code == 200, listed.text
    leads = listed.json().get("leads", [])
    if not leads:
        pytest.skip("no leads in this database to compare against")

    engaged = [lead for lead in leads if lead.get("engagement_type")]
    if not engaged:
        pytest.skip("no lead in this database records an engagement type")

    lead = engaged[0]
    timeline = client.get(f"/api/v1/crm/leads/{lead['id']}/timeline")
    assert timeline.status_code == 200, timeline.text
    payload = timeline.json()

    assert payload["lead"].get("engagement_type"), (
        "the timeline dropped the engagement the stream card displays"
    )
    # This is the condition, not a requirement. A lead with real timeline rows
    # is fine and takes the other branch.
    if payload.get("interactions"):
        pytest.skip("this lead has timeline rows, so the fallback is not exercised")


def test_the_dossier_reports_the_capture_engagement():
    """
    The contradiction itself: an empty table must not be reported as an empty
    history when the lead records how it was captured.
    """
    source = _source(LEADS_SURFACE)

    empty_branch = re.search(
        r"interactions\.length === 0 \?(.{0,1400}?)\) : \(", source, re.DOTALL
    )
    assert empty_branch, "the empty interactions branch has moved or been rewritten"
    branch = empty_branch.group(1)

    assert "lead.engagement_type" in branch, (
        "the dossier declares an empty history without consulting the engagement "
        "the stream card shows, which is the contradiction this guards"
    )
    assert "NO INTERACTIONS RECORDED" in branch, (
        "a lead with no engagement and no timeline still has to say so plainly "
        "rather than render an empty section"
    )


def test_the_dossier_does_not_date_the_engagement_it_cannot_date():
    """
    Nothing invented on screen.

    created_at is when the studio recorded the lead. It is not when the person
    engaged, which is not stored, so it may be shown as a capture date and must
    not be labelled as the moment of the interaction.
    """
    source = _source(LEADS_SURFACE)

    # Scoped to the fallback, not to the file. The word CAPTURED also appears
    # in the empty stream copy ("NO LEADS CAPTURED YET"), so a search across
    # the whole source passes whether or not this branch exists at all, which
    # is the shape of guard this repository has been caught by before.
    empty_branch = re.search(
        r"interactions\.length === 0 \?(.{0,1400}?)\) : \(", source, re.DOTALL
    )
    assert empty_branch, "the empty interactions branch has moved or been rewritten"
    branch = empty_branch.group(1)

    assert re.search(r"CAPTURED \{lead\.created_at", branch), (
        "the fallback date is not labelled as a capture, so it reads as the time "
        "of an engagement the studio never recorded"
    )
    assert "interacted_at" not in branch, (
        "the fallback is claiming an interaction timestamp, which only exists "
        "for rows that are actually in the timeline"
    )


# ---------------------------------------------------------------------------
# 2. The swipe card does not print one value twice
# ---------------------------------------------------------------------------


def test_the_seeded_specimens_repeat_their_category():
    """
    Establishes the condition. Every seeded specimen carries topic == archetype,
    which is what made the duplicated label universal rather than occasional.
    """
    response = client.get("/api/inspirations")
    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload.get("inspirations") or payload.get("templates") or []
    if not rows:
        pytest.skip("no specimens in this database")

    identical = [
        row for row in rows
        if str(row.get("archetype", "")).strip().lower()
        == str(row.get("topic", "")).strip().lower()
    ]
    assert identical, (
        "no specimen repeats its category any more, so the guard below is no "
        "longer describing this data"
    )


def test_the_swipe_card_compares_before_printing_both():
    """
    A separator with the same word on both sides tells a reader nothing. The
    card has to compare the two fields rather than concatenate them.
    """
    source = _source(SWIPE_SURFACE)

    assert "specimen.topic" in source, "the card no longer shows a topic at all"
    comparison = re.search(
        r"specimen\.topic[^\n]*!==[^\n]*specimen\.archetype"
        r"|specimen\.archetype[^\n]*!==[^\n]*specimen\.topic",
        source,
    )
    assert comparison, (
        "the card prints archetype and topic unconditionally, which renders the "
        "same word twice for every specimen the product seeds"
    )
