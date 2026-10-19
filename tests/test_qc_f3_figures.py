"""
Figures read from LinkedIn pages in any language.
=================================================

BRIDGE-05  On a German or Italian page "8.210" means eight thousand two
           hundred and ten. The readers took "." as a decimal point, so 8.210
           followers was stored as 8, marked exact, and the profile reader did
           the same to the top card's follower count. A figure is now read
           with the page's own separators, and one that cannot be read with
           certainty is not stored at all.

These run the shipped scripts in headless Chromium (see qc_f3_pages.py).
"""

import pytest

from qc_f3_pages import Pages, page_html

PARSE = """(cases) => cases.map((c) => { const r = parseMetricValue(c); return r ? [r.value, r.precision] : null; })"""


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _parse(pages, lang, cases):
    page = pages.open("/analytics/creator/content/", page_html("<main></main>", lang=lang),
                      scripts=("voyager_schema.js", "content.js"))
    out = page.evaluate(PARSE, cases)
    page.context.close()
    return dict(zip(cases, [tuple(v) if v else None for v in out]))


def test_a_german_page_reads_its_thousands_separator():
    p = Pages()
    try:
        got = _parse(p, "de-DE", ["8.210", "12.345", "1.234.567", "1,2K", "3,5 Tsd.", "1,2 Mio.", "412", "12,345", "1.234,5"])
    finally:
        p.close()
    assert got["8.210"] == (8210, "exact")
    assert got["12.345"] == (12345, "exact")
    assert got["1.234.567"] == (1234567, "exact")
    assert got["1,2K"] == (1200, "rounded")
    assert got["3,5 Tsd."] == (3500, "rounded")
    assert got["1,2 Mio."] == (1200000, "rounded")
    assert got["412"] == (412, "exact")
    # A comma with three digits after it has no certain reading on a German
    # page, and a count with a fraction and no suffix is not a count.
    assert got["12,345"] is None
    assert got["1.234,5"] is None


def test_an_italian_and_a_french_page(pages):
    italian = _parse(pages, "it", ["8.210", "1,5 Mln"])
    assert italian["8.210"] == (8210, "exact")
    assert italian["1,5 Mln"] == (1500000, "rounded")
    french = _parse(pages, "fr-FR", ["12 345", "8 210", "1,2 k"])
    assert french["12 345"] == (12345, "exact")
    assert french["8 210"] == (8210, "exact")
    assert french["1,2 k"] == (1200, "rounded")


def test_an_english_page_is_read_as_before(pages):
    got = _parse(pages, "en", ["48,200", "1,234", "1.2K", "13K", "1.5M", "892"])
    assert got == {"48,200": (48200, "exact"), "1,234": (1234, "exact"), "1.2K": (1200, "rounded"),
                   "13K": (13000, "rounded"), "1.5M": (1500000, "rounded"), "892": (892, "exact")}


def test_a_dotted_figure_on_a_page_of_unknown_language_is_refused(pages):
    # LinkedIn names its language on <html>. Without it, "8.210" is either
    # 8210 or eight point two one, and neither is certain enough to store.
    got = _parse(pages, None, ["8.210", "12.345", "1,2K", "1,234"])
    assert got["8.210"] is None and got["12.345"] is None and got["1,2K"] is None
    assert got["1,234"] == (1234, "exact")


def _analytics(lang, cards):
    body = "<main><button class='artdeco-dropdown__trigger'>Letzte 24 Stunden</button>"
    for value, label in cards:
        body += f"<div data-test-metric-card><span data-test-metric-value>{value}</span> <span>{label}</span></div>"
    return page_html(body + "</main>", title="Analytics | LinkedIn", lang=lang)


def test_a_german_analytics_page_sends_the_real_figures(pages):
    page = pages.open("/analytics/creator/content/",
                      _analytics("de", [("12.345", "Impressionen"), ("8.210", "Follower insgesamt")]),
                      storage={"signedInVanity": "test-creator"})
    page.clock.run_for(5000)
    sent = pages.sent(page, "/api/analytics/ingest")
    assert sent, "the German analytics page was not read"
    row = sent[-1]["series"][0]
    assert row["impressions"] == 12345
    assert row["followers"] == 8210


def test_an_unlabelled_dotted_page_sends_no_figure_below_a_thousand(pages):
    page = pages.open("/analytics/creator/content/",
                      _analytics(None, [("12.345", "Impressionen"), ("8.210", "Follower insgesamt")]),
                      storage={"signedInVanity": "test-creator"})
    page.clock.run_for(5000)
    for body in pages.sent(page, "/api/analytics/ingest"):
        for row in body["series"]:
            assert row["impressions"] in (None, 12345)
            assert row["followers"] in (None, 8210)


PROFILE = """
<main><section aria-label="Primary content"><section>
  <h2>Test Creator</h2>
  <div>Founder at Local-First Labs</div>
  <div>Berlin, Deutschland</div>
  <a href="/in/test-creator/overlay/contact-info/">Contact info</a>
  <div>8.210 Follower</div>
  <div>1.204 connections</div>
</section></section></main>
"""


def test_the_profile_top_card_reads_a_german_follower_count(pages):
    page = pages.open("/in/test-creator/", page_html(PROFILE, title="Test Creator | LinkedIn", lang="de"),
                      scripts=("voyager_schema.js", "content.js", "own_pages.js"))
    page.clock.run_for(4000)
    observed = pages.sent(page, "/api/v1/identity/observe")
    assert observed, "the creator's profile was not read"
    assert observed[0]["follower_count"] == 8210
    assert observed[0]["connection_count"] == 1204


def test_the_profile_top_card_refuses_a_dotted_count_of_unknown_language(pages):
    page = pages.open("/in/test-creator/", page_html(PROFILE, title="Test Creator | LinkedIn"),
                      scripts=("voyager_schema.js", "content.js", "own_pages.js"))
    page.clock.run_for(4000)
    observed = pages.sent(page, "/api/v1/identity/observe")
    assert observed
    assert observed[0]["follower_count"] is None


# Review of BRIDGE-05: Indian lakh and crore grouping ("12,34,567") was read
# correctly before the locale parser and refused by it.

def test_indian_grouping_is_read_as_before(pages):
    for lang in ("en", "en-IN", "hi", None):
        got = _parse(pages, lang, ["12,34,567", "1,23,456", "1,00,00,000", "12,345"])
        assert got["12,34,567"] == (1234567, "exact"), lang
        assert got["1,23,456"] == (123456, "exact"), lang
        assert got["1,00,00,000"] == (10000000, "exact"), lang
        assert got["12,345"] == (12345, "exact"), lang
    # Where the comma is the decimal mark it is still not a thousands grouping.
    german = _parse(pages, "de", ["12,34,567", "1.234.567"])
    assert german["12,34,567"] is None and german["1.234.567"] == (1234567, "exact")


def test_the_profile_top_card_reads_an_indian_follower_count(pages):
    body = PROFILE.replace("8.210 Follower", "1,23,456 followers").replace("1.204 connections", "500+ connections")
    page = pages.open("/in/test-creator/", page_html(body, title="Test Creator | LinkedIn", lang="en-IN"),
                      scripts=("voyager_schema.js", "content.js", "own_pages.js"))
    page.clock.run_for(4000)
    observed = pages.sent(page, "/api/v1/identity/observe")
    assert observed and observed[0]["follower_count"] == 123456
