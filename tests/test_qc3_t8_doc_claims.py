"""
The claims this batch retired, asserted so they cannot come back.
================================================================

T8's first pass replaced "the scripts never click" with "outside the one
exception below, they never click", and that was still false: there are two
places where a content script clicks and types, not one. The import also opens
a page, which one help article disclosed and the store-facing documents denied.
The review sent both back. These tests hold the corrected claims in place.

What is asserted here is a document's words, because the words are the
deliverable. Each one names the code that makes the claim true or false:

  own_pages.js clickShowMore -> button.click(), the load-more control
  own_pages.js window.location.href = finishRes.next_url, the self-navigation
  content.js startPostBtn.click() then typing, the composer insert
  linkedin_client.schedule_norm_share, the write to LinkedIn's private API

The store folder (~/.cache/inox-qc2/store) is outside the repository, so those
assertions skip when it is absent rather than failing a clean checkout.
"""

import os

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STORE = os.path.expanduser("~/.cache/inox-qc2/store")

EXTENSION_DOC = os.path.join(REPO, "docs", "EXTENSION_AND_SYNC.md")
ARCHITECTURE = os.path.join(REPO, "docs", "ARCHITECTURE.md")
REGISTER = os.path.join(REPO, "planning", "7 Roadmap", "Risk - LinkedIn terms and detection.md")
HELP = os.path.join(REPO, "docs", "help")


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def store(name):
    path = os.path.join(STORE, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} is outside the repository and not present here")
    return read(path)


# ---------------------------------------------------------------------------
# The extension document
# ---------------------------------------------------------------------------

def test_the_extension_document_claims_no_unconditional_never_click():
    """
    The sentence this batch exists to retire, in both the forms it has taken:
    the original unconditional one, and the first replacement, which allowed
    exactly one exception when there are two.
    """
    text = read(EXTENSION_DOC)
    assert "They never click, type" not in text
    assert "Outside the one exception below" not in text, (
        "the one-exception wording is back; the composer insert is a second one"
    )
    assert "with two named exceptions" in text
    assert "They click and type in exactly two places" in text


def test_the_extension_document_names_both_things_that_act_on_the_page():
    text = read(EXTENSION_DOC)
    assert "History import (first exception)" in text
    assert "Placing a draft (second exception)" in text
    # The import's three acts, each verified in own_pages.js.
    assert "Show more results" in text
    assert "250 rounds" in text
    assert "window.location.href" in text, "the self-navigation is not disclosed"
    # The insert's two, verified in content.js.
    assert "Start a post" in text
    assert "It never presses **Post**" in text


def test_the_extension_document_does_not_carve_network_reading_out_of_no_requests():
    """
    The reviewer's note on T8-2. The row read "None of the extension's own
    fetches, outside network reading above", which implies network reading
    issues a request to LinkedIn. It does not: voyager_interceptor.js wraps
    window.fetch and copies answers the page already had, and the row below it
    says so.
    """
    text = read(EXTENSION_DOC)
    assert "outside network reading above" not in text
    assert "network reading included" in text


def test_the_extension_document_scopes_its_no_timer_claim():
    """
    "Nothing runs on a timer" was stated absolutely in a section about session
    sync, while background.js drains kept captures every minute and
    own_pages.js sends a heartbeat every minute.
    """
    text = read(EXTENSION_DOC)
    assert "\nNothing runs on a timer." not in text
    assert "Nothing about your session runs on a timer." in text
    assert "DRAIN_EVERY_MINUTES" in text and "HEARTBEAT_MS" in text


# ---------------------------------------------------------------------------
# The architecture document and the register
# ---------------------------------------------------------------------------

def test_the_architecture_document_counts_the_automation_correctly():
    """
    "Zero automated bot activity" became "Two automated paths exist", which
    was a count, and the count was wrong once the composer insert is included.
    """
    text = read(ARCHITECTURE)
    assert "Zero automated bot activity" not in text
    assert "Two automated paths exist" not in text
    assert "Three things act rather than read" in text
    assert "schedule_norm_share" in text


def test_the_register_does_not_contradict_itself():
    """
    The register's opening said the product "never posts or messages" four
    lines above this batch's own paragraph describing automated content
    creation through LinkedIn's private API.
    """
    text = read(REGISTER)
    assert "never posts or messages" not in text
    assert "It never comments, reacts, connects or messages." in text
    assert "schedule_norm_share" in text
    opening, _, rest = text.partition("**Most exposed:**")
    assert "Send to LinkedIn" in opening, (
        "the opening paragraph no longer admits the one thing that does post"
    )


# ---------------------------------------------------------------------------
# The store folder: the policy and the listing a reviewer reads
# ---------------------------------------------------------------------------

def test_the_privacy_policy_does_not_deny_opening_a_page():
    policy = store("PRIVACY_POLICY.md")
    assert "does not open a page for you" not in policy
    assert "it moves the tab" in policy and "activity pages to the next" in policy
    assert "So it does open a\npage for you" in policy
    # And the composer insert, which the policy's own composer paragraph
    # describes, is no longer contradicted by a "one action" claim.
    assert "it is the one action here" not in policy
    assert 'clicks\nLinkedIn\'s own "Start a post" control' in policy


def test_the_store_listing_does_not_claim_it_clicks_nothing():
    """
    The highest-consequence instance: this is the text a store reviewer is
    given. All three claims were false against own_pages.js.
    """
    listing = store("SUBMISSION.md")
    for claim in (
        "click anything on your behalf",
        "no automated action on the user's account",
        "The extension reads only pages the user has navigated to themselves.",
        "It does not browse, crawl, connect, message, comment or act on the user's account.",
    ):
        assert claim not in listing, f"a retired claim is back in the store listing: {claim!r}"


def test_the_store_listing_discloses_the_import_and_the_insert():
    listing = store("SUBMISSION.md")
    assert "Import your history" in listing
    # The three places that denied it: the store description, the host
    # permission justification, and the answers for review.
    disclosures = listing.count("Show more results") + listing.count("load-more control")
    assert disclosures >= 3, (
        f"the import is disclosed in {disclosures} places; all three that denied it must say it"
    )
    assert "Start a post" in listing
    assert "no crawling" in listing or "does not crawl" in listing


# ---------------------------------------------------------------------------
# The help sweep: no article sends a creator to a section that is gone
# ---------------------------------------------------------------------------

def _help_files():
    return sorted(
        os.path.join(HELP, name) for name in os.listdir(HELP) if name.endswith(".md")
    )


def test_no_help_article_sends_a_creator_to_a_removed_section():
    """
    The Swipe File and Command sections are gone from the merged tree's rail
    (studio/ui/src/lib/navigation.ts). This is asserted as words rather than
    against the rail, because this branch predates that deletion: the articles
    describe where the tree they land in actually is.
    """
    phrases = (
        "Open **Swipe File**",
        "in **Swipe File** on the rail",
        "Choose **Command** in the rail",
        "Open **Command** from the rail",
        "the Command console",
        "reopen **Swipe File**",
    )
    offences = []
    for path in _help_files():
        text = read(path)
        for phrase in phrases:
            if phrase in text:
                offences.append(f"{os.path.basename(path)}: {phrase!r}")
    assert not offences, "help still routes a creator to a section that is gone: " + "; ".join(offences)

    # And the rail table a creator reads on their first run lists neither.
    # Checked on that one file, because "| Command |" is also the heading of
    # every shell-command table in the CLI articles.
    rail_table = read(os.path.join(HELP, "open-the-studio-for-the-first-time.md"))
    assert "| Swipe File |" not in rail_table
    assert "| Command | Agent runs" not in rail_table


def test_the_swipe_file_article_is_gone_and_nothing_links_to_it():
    assert not os.path.exists(os.path.join(HELP, "browse-the-swipe-file.md"))
    for path in _help_files():
        assert "browse-the-swipe-file.md" not in read(path), f"{path} links to a deleted article"
    docs_engine = read(os.path.join(REPO, "studio", "backend", "docs_engine.py"))
    assert "browse-the-swipe-file.md" not in docs_engine


def test_no_help_article_calls_the_import_the_only_thing_that_acts():
    """
    The reviewer's notes on T8-8. Two articles said the import was the one
    thing the bridge does to a page, which content.js:279 contradicts, and one
    of them attributed the click on LinkedIn's own control to the creator,
    who presses Import in the studio.
    """
    leaves = read(os.path.join(HELP, "what-leaves-this-machine.md"))
    assert "That import is the one thing it does to the page" not in leaves
    assert "your click on LinkedIn's control" not in leaves
    assert "Its click on LinkedIn's control, not yours" in leaves

    setup = read(os.path.join(HELP, "set-up-the-studio-from-your-linkedin.md"))
    assert "Scrolling is the one thing the studio does on LinkedIn" not in setup
    assert "the one other thing it does to a page" in setup


def test_the_command_article_describes_the_prompt_panel():
    text = read(os.path.join(HELP, "run-an-instruction-on-your-draft.md"))
    assert "**Prompt** tab" in text
    assert "Include my draft" in text
    assert "No model is set up, so nothing was written for this instruction." in text, (
        "the article still promises a local template for the no-model case"
    )
    assert "Zero manual intervention" not in text, "the fixed template post is back"
    assert "block of JSON" not in text


def test_brand_studio_is_described_with_all_six_tabs():
    text = read(os.path.join(HELP, "set-up-brand-studio.md"))
    assert "four tabs" not in text
    assert "six tabs" in text
    for tab in ("Identity", "Watermark", "Grounding", "Local security", "Storage and privacy", "Licence"):
        assert tab in text, f"{tab} is not named"


def test_the_posts_and_patterns_help_matches_the_rebuilt_screens():
    """T6-N2: the two articles that cycle 3 made false."""
    text = read(os.path.join(HELP, "see-what-worked-and-where-your-attention-goes.md"))
    # The settle age is measured per install, not a fixed week.
    assert "at least a week old" not in text
    assert "posts older than the age at which your posts settle" in text
    # The table, and its controls, which the article denied having.
    for control in ("Search your posts", "Settled state", "Sort", "PAGE 1 OF"):
        assert control in control and control in text, f"{control} is not described"
    assert "UNDERPERFORMED" in text
    # The sample floor moved from three to eight, so the number is no longer
    # stated here: the screen prints its own.
    assert "at least three posts have it and three do not" not in text


def test_the_analytics_help_no_longer_promises_three_observations():
    text = read(os.path.join(HELP, "read-your-analytics.md"))
    assert "## The three observations" not in text
    assert "## The panels beside the figures" in text
    assert "your post with the highest engagement rate." not in text
    assert "your strongest post across all of your posts whose figures have settled" in text
