"""
What the creator learns reaches what they write.
================================================

MAKING.md section 1.11 and M-11: of seven text generators, the only one that
puts "what worked" into a prompt is the copilot, on a route no screen calls,
and the screens holding the knowledge offer no way to act on it
("ACTIONS ON PATTERNS []"). The Composer, where the writing happens, could
reach the one 10 KB brief that answers "which of my posts worked" only
through a tab in the inspector beside the editor.

The Composer now opens on the creator's own strongest openings, with the
figures that make them the strongest and the shape each post was set in, and
one control puts one of them in the editor. Everything on it is the creator's
own published text, said to be theirs; nothing is generated and nothing is a
forecast.
"""

import os

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401

COMPOSER = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "studio", "ui", "src", "components", "ComposerCanvas.tsx",
)


def test_the_composer_reads_the_evidence_brief_and_says_whose_words_these_are():
    with open(COMPOSER, encoding="utf-8") as handle:
        source = handle.read()
    assert "fetchEvidenceBrief" in source, "the Composer does not read what worked"
    # Labelled as the creator's own measured history, which is the whole
    # difference between this and a model's suggestion.
    assert "What worked, from your own posts" in source
    assert "not a suggestion from a model" in source
    assert "not a forecast" in source
    # Offered, not applied behind the writer's back, and reversible.
    assert "Use this opening" in source
    assert "swapOpening" in source
    assert "UNDO" in source


def test_the_composer_offers_the_creator_their_own_strongest_opening(studio):
    """
    Driven, because a panel that reads an endpoint and prints nothing would
    pass a source check. Five posts of the creator's own are seeded, so the
    brief has settled posts to rank.
    """
    seed_creator(studio["client"], commenter=None)
    page = open_section(studio, "composer")

    panel = page.locator("section[aria-labelledby=composer-what-worked]")
    expect(panel).to_be_visible(timeout=10000)
    # Folded when the Composer opens, so that the editor is on screen; the
    # writer asks for it and it is there.
    panel.get_by_role("button", name="SHOW").click()
    expect(panel).to_contain_text("not a suggestion from a model")

    use = panel.get_by_role("button", name="Use this opening").first
    expect(use).to_be_visible(timeout=10000)
    offered = panel.locator("li").first.locator("p").first.inner_text()
    assert offered.strip(), "an opening was offered with no text in it"

    use.click()
    editor = page.locator('[aria-label="Post body"]')
    expect(editor).to_have_value(offered, timeout=5000)

    # The way back, as fast as the way in.
    panel.get_by_role("button", name="Undo the opening and put your own words back").click()
    expect(editor).to_have_value("", timeout=5000)
    assert studio["errors"] == [], studio["errors"]


def test_the_figures_beside_an_opening_are_the_ones_the_server_measured(studio):
    """Reactions, comments and qualified leads, under those names. No rating."""
    seed_creator(studio["client"], commenter=None)
    page = open_section(studio, "composer")
    panel = page.locator("section[aria-labelledby=composer-what-worked]")
    expect(panel).to_be_visible(timeout=10000)
    panel.get_by_role("button", name="SHOW").click()
    expect(panel).to_contain_text("reactions", timeout=10000)
    text = panel.inner_text()
    assert "reactions" in text
    assert "qualified leads" in text
    assert "characters" in text and "paragraph" in text, "the shape of the post is not stated"
    # The vault's editorial rating has no business here: these are posts,
    # not hook forms, and nobody rated them.
    assert "EDITOR'S RATING" not in text


def test_adding_the_engineering_pack_keeps_half_the_rail_for_the_creators_own_forms(studio):
    """
    MAKING.md M-1, driven in the real Composer: one click of "Add the
    engineering pack" used to replace all twelve of the creator's neutral
    starter forms in the hook rail, because the server ranks by a score only
    the pack carries. The pack now adds to the rail and is named on it.
    """
    client = studio["client"]
    # The library seeds its neutral starter forms the first time it is read,
    # which on a real install has happened long before anyone opts into the
    # pack: the control that adds it is on a screen that reads the library.
    starters = client.get("/api/v1/intelligence/templates?limit=200").json()["templates"]
    assert starters and all(t["velocity_score"] is None for t in starters), starters[:1]

    added = client.post("/api/v1/intelligence/packs/engineering", json={"enabled": True})
    assert added.status_code == 200, added.text

    page = open_section(studio, "composer")
    rail = page.locator('section[aria-label="Hook archetypes"]')
    expect(rail).to_be_visible(timeout=10000)
    cards = page.locator('[aria-label^="Apply "]')
    expect(cards.first).to_be_visible(timeout=10000)

    counted = page.evaluate(
        """() => {
          const cards = Array.from(document.querySelectorAll('[aria-label^="Apply "]'));
          return {
            total: cards.length,
            pack: cards.filter((c) => / PACK\\b/.test(c.innerText)).length,
          };
        }"""
    )
    assert counted["total"] == 12, counted
    assert counted["pack"] > 0, "the opt-in pack never reached the rail"
    assert counted["total"] - counted["pack"] >= 6, (
        f"the pack evicted the creator's own forms: {counted}"
    )
    # The warning is where the keystroke is, not only on the Swipe File screen.
    expect(rail).to_contain_text("first-person claims")
    # And what these specimens are at all, which was the Swipe File's one
    # honest sentence and had nowhere else to live once that screen went.
    expect(rail).to_contain_text("not posts anyone measured")
    expect(rail).to_contain_text("typed in by whoever wrote the form")
    assert studio["errors"] == [], studio["errors"]


def test_the_pack_can_be_taken_back_out_of_the_rail(studio):
    """
    Its control was on the Swipe File, which is gone. Without this, a creator
    who had added the pack could never get back to their own forms.
    """
    client = studio["client"]
    starters = client.get("/api/v1/intelligence/templates?limit=200").json()["templates"]
    assert starters
    assert client.post("/api/v1/intelligence/packs/engineering", json={"enabled": True}).status_code == 200

    page = open_section(studio, "composer")
    rail = page.locator('section[aria-label="Hook archetypes"]')
    expect(rail).to_be_visible(timeout=10000)
    expect(rail).to_contain_text("PACK")

    rail.get_by_role("button", name="Remove the engineering pack").click()
    # The rail is the creator's own again, and what happened is still said.
    expect(rail).to_contain_text("Removed", timeout=10000)
    counted = page.evaluate(
        """() => {
          const cards = Array.from(document.querySelectorAll('[aria-label^="Apply "]'));
          return { total: cards.length, pack: cards.filter((c) => / PACK\\b/.test(c.innerText)).length };
        }"""
    )
    assert counted["pack"] == 0, counted
    assert counted["total"] == len(starters[:12]), counted
    # Nothing offers to put another author's first-person claims back.
    assert "Add the engineering pack" not in rail.inner_text()
    assert studio["errors"] == [], studio["errors"]


def test_with_too_few_settled_posts_the_panel_says_so_rather_than_inventing(studio):
    """The honesty rule: a brief with no evidence prints the server's reason."""
    page = open_section(studio, "composer")
    panel = page.locator("section[aria-labelledby=composer-what-worked]")
    expect(panel).to_be_visible(timeout=10000)
    panel.get_by_role("button", name="SHOW").click()
    page.wait_for_timeout(400)
    text = panel.inner_text()
    assert "Use this opening" not in text, "an opening was offered with no settled posts to draw it from"
    assert "reactions" not in text.lower() or "Not enough" in text
    assert studio["errors"] == [], studio["errors"]
