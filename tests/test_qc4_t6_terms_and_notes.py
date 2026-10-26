"""
Item 30: LinkedIn's own words, and the notes that read them.
============================================================

The creator-facing page quotes LinkedIn's User Agreement and Help Center
verbatim and dated, beside each feature's standing; the risk note and the
competitive landscape say "tolerated in practice, not permitted in text"
and carry the dated enforcement record. The quotes are held here to the
research note's text, fetched 2026-10-26, so a paraphrase cannot replace a
quotation without the suite saying so.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARTICLE = os.path.join(REPO_ROOT, "docs", "help", "where-each-feature-stands-with-linkedins-terms.md")
RISK = os.path.join(REPO_ROOT, "planning", "7 Roadmap", "Risk - LinkedIn terms and detection.md")
LANDSCAPE = os.path.join(REPO_ROOT, "planning", "7 Roadmap", "Competitive Landscape.md")

# Verbatim, from the User Agreement effective on November 3, 2025 (8.2 items
# 1, 2, 4, 13 and 15) and the two Help Center articles, as fetched.
VERBATIM = (
    "Create a false identity on LinkedIn, misrepresent your identity, create a Member profile for anyone other "
    "than yourself (a real person), or use or attempt to use another's account (such as sharing log-in "
    "credentials or copying cookies);",
    "Develop, support or use software, devices, scripts, robots or any other means or processes (such as "
    "crawlers, browser plugins and add-ons or any other technology) to scrape or copy the Services, including "
    "profiles and other data from the Services;",
    "Copy, use, display or distribute any information (including content) obtained from the Services, whether "
    "directly or through third parties (such as search tools or data aggregators or brokers), without the "
    "consent of the content owner (such as LinkedIn for content it owns);",
    "Use bots or other unauthorized automated methods to access the Services, add or download contacts, send "
    "or redirect messages, create, comment on, like, share, or re-share posts, or otherwise drive inauthentic "
    "engagement;",
    "Overlay or otherwise modify the Services or their appearance (such as by inserting elements into the "
    "Services or removing, covering, or obscuring an advertisement included on the Services);",
    "In order to protect our members' data and our website, we don't permit the use of any third party "
    "software, including \"crawlers\", bots, browser plug-ins, or browser extensions that scrape, modify the "
    "appearance of, or automate activity on LinkedIn's website.",
    "Any member who uses tools for such purposes is in violation of the User Agreement. This means that they "
    "risk having their accounts restricted or shut down. They also risk the possibility that any prohibited "
    "tools they're using may become non-operational without notice.",
    "we don't allow the use of third-party software or browser extensions that scrape, modify the appearance "
    "of, or automate activity on LinkedIn's website.",
)

VERBATIM = VERBATIM + (
    "Reverse engineer, decompile, disassemble, decipher or otherwise attempt to derive the source code for the "
    "Services or any related technology that is not open source;",
)

DATES = ("effective on November 3, 2025", "26 October 2026", "Last updated: 2 years ago",
         "Last updated: 3 weeks ago", "a1341387", "90586")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _flat(text):
    return " ".join(text.split())


def test_the_article_quotes_linkedin_verbatim():
    article = _flat(_read(ARTICLE))
    missing = [quote[:60] for quote in VERBATIM if quote not in article]
    assert not missing, f"the article no longer quotes these verbatim: {missing}"


def test_the_quotes_are_dated_and_sourced():
    article = _read(ARTICLE)
    for mark in DATES:
        assert mark in article, f"the article does not say {mark!r}"
    assert "None of it is legal advice" in article


def test_each_feature_has_its_standing():
    article = _flat(_read(ARTICLE))
    for standing in ("Tolerated in practice, not permitted in text", "Opt-in", "first creator profile only",
                     "Nothing acts on LinkedIn except when you press Insert", "Outside the words quoted here"):
        assert standing in article, f"the article lost the standing {standing!r}"
    # The words beside the switch are the popup's own, quoted as it shows them.
    with io.open(os.path.join(REPO_ROOT, "studio", "extension", "popup.js"), encoding="utf-8") as handle:
        popup = _flat(handle.read().replace('" +\n', "").replace('"', ""))
    assert "which LinkedIn may treat as automation" in popup
    assert "which LinkedIn may treat as automation" in article


def test_the_risk_note_starts_the_lawyer_from_the_right_place():
    note = _read(RISK)
    assert "That is a defensible personal tool." not in note
    flat = _flat(note)
    assert "tolerated in practice, not permitted in text" in flat
    assert "Shield wound down in May 2026" in flat
    assert "2025-06-20" in flat


def test_the_landscape_says_what_happened_to_shield_and_kleo():
    landscape = _flat(_read(LANDSCAPE))
    assert "status uncertain" not in landscape
    assert "Wound down May 2026" in landscape
    assert "2025-06-20" in landscape and "jakezward" in landscape, "Kleo's date lost its source"
    assert "tolerated in practice, not permitted in text" in landscape


def test_linkedins_item_numbers_survive_the_studios_renderer():
    """
    The items were first written as an ordered list numbered 1, 2, 4, 13 and
    15, and the studio's markdown renderer numbers a list from its first
    marker, so a reader saw items 13 and 15 labelled 4 and 5. Each item now
    carries its number as text.
    """
    article = _read(ARTICLE)
    for number in (1, 2, 4, 9, 13, 15):
        assert f"**Item {number}:**" in article, f"item {number} does not carry LinkedIn's own number"
    import re
    assert not re.search(r"^1[35]\. ", article, re.M), "an item number is a list marker again"


# ---------------------------------------------------------------------------
# Review round, SF-6: the one mark the extension makes in LinkedIn's page
# ---------------------------------------------------------------------------

ITEM_9 = ("Reverse engineer, decompile, disassemble, decipher or otherwise attempt to derive the source code for the "
          "Services or any related technology that is not open source;")


def test_the_article_names_the_data_urn_mark_with_its_standing():
    """
    card_urns.js runs in LinkedIn's own page context on every LinkedIn page,
    from installation, and writes a data-urn attribute onto feed cards. The
    article listed page changes only under network reading, so a reader
    concluded nothing touched the page by default. Under decision D3 it is
    the one mark the extension makes there, with the import banner while an
    import runs.
    """
    article = _flat(_read(ARTICLE))
    manifest = _read(os.path.join(REPO_ROOT, "studio", "extension", "manifest.json"))
    assert '"card_urns.js"' in manifest and '"world": "MAIN"' in manifest, "the mark's script changed; revisit"
    assert "`data-urn`" in article and "inside LinkedIn's own page code" in article
    assert "the one mark the extension makes in LinkedIn's page" in article
    assert "Yes, on every LinkedIn page" in article
    assert ITEM_9 in article and "**Item 9:**" in _read(ARTICLE)
    assert "The capture notice" not in article, "the capture notice moved to the badge and the side panel (D3)"


def test_the_imports_are_not_called_permitted():
    """Note N-16: the text leaves item 4 open for LinkedIn's computed figures and others' connections."""
    article = _flat(_read(ARTICLE))
    assert "Permitted by the text" not in article
    assert "Touches none of the words quoted here" in article


def test_the_background_claim_says_what_runs_there():
    """Note N-17: the worker notices sign-in changes and retries held captures; it never acts on LinkedIn."""
    article = _flat(_read(ARTICLE))
    assert "never runs in the background" not in article
    assert "never acts on LinkedIn in the background" in article


# ---------------------------------------------------------------------------
# Review round, SF-7: every quotation in the notes has a source to check
# ---------------------------------------------------------------------------

import re as _re

QUOTED = _re.compile(r'"([^"\n]+)"')


def _unsourced(text):
    """Quotations of four words or more in a paragraph or table row that names no source address."""
    found = []
    for block in _re.split(r"\n\s*\n|\n(?=\|)", _re.sub(r"`[^`\n]*`", "", text)):
        if "http://" in block or "https://" in block:
            continue
        found += [quote for quote in QUOTED.findall(block) if len(quote.split()) >= 4]
    return found


def test_every_quotation_in_the_two_notes_names_a_source_the_reader_can_check():
    """
    Review finding SF-7: the risk note put a dated, verbatim sentence in a
    co-founder's mouth with no address. Each quotation now carries the
    address it can be checked at, in the same paragraph or table row.
    """
    for path in (RISK, LANDSCAPE):
        assert _unsourced(_read(path)) == [], f"{os.path.basename(path)} quotes without a source"


def test_the_quotation_guard_can_fail():
    assert _unsourced('A paragraph that says "these words were never written anywhere".') == [
        "these words were never written anywhere"]
    assert _unsourced('| row | "four words quoted here" | no address |') == ["four words quoted here"]
    assert _unsourced('"four words quoted here" https://example.com/source') == []


def test_kleos_post_is_cited_where_it_can_be_read():
    note = _read(RISK)
    assert "https://www.linkedin.com/posts/jakezward_i-didnt-want-to-post-this-but-i-have-to-activity-7341796212687175681-JjZx" in note
    assert "2025-06-20" in note
