"""
The creator analytics page, as the bridge reads it.
===================================================

BRIDGE-11  "Past 365 days" was not recognised, so a year's impressions were
           sent with no window, stored under today's date and charted as one
           day. Every range label LinkedIn prints is now read, in English and
           the other languages it serves, and a range control whose words are
           not understood marks the figures as of an unrecognised window, which
           the studio refuses as a daily figure.
BRIDGE-15  The page said "creator analytics synced to your local studio" for
           any answer, including none: the studio not running, or refusing a
           browser it was never paired with.

These run the shipped content.js in headless Chromium (see qc_f3_pages.py).
"""

import pytest

from qc_f3_pages import Pages, page_html, toast_text

INGEST = "/api/analytics/ingest"


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


# Figures with no separator read the same in every language.
def analytics(range_label, cards=(("4820", "Impressions"), ("3105", "Total followers")), lang="en"):
    body = "<main>"
    if range_label is not None:
        body += f"<button class='artdeco-dropdown__trigger'>{range_label}</button>"
    for value, label in cards:
        body += f"<div data-test-metric-card><span data-test-metric-value>{value}</span> <span>{label}</span></div>"
    return page_html(body + "</main>", title="Analytics | LinkedIn", lang=lang)


def _period(pages, label, lang="en"):
    page = pages.open("/analytics/creator/content/", analytics(label, lang=lang),
                      storage={"signedInVanity": "test-creator"})
    page.clock.run_for(5000)
    sent = pages.sent(page, INGEST)
    page.context.close()
    assert sent, f"the page with range {label!r} was not read"
    return sent[-1]["period_label"]


@pytest.mark.parametrize("label, expected", [
    ("Past 24 hours", "1d"),
    ("Past 7 days", "7d"),
    ("Past 14 days", "14d"),
    ("Past 28 days", "28d"),
    ("Past 90 days", "90d"),
    ("Past 365 days", "365d"),
    ("Past 12 months", "365d"),
    ("Past year", "365d"),
])
def test_every_english_range_is_recognised(pages, label, expected):
    assert _period(pages, label) == expected


@pytest.mark.parametrize("label, lang, expected", [
    ("Letzte 7 Tage", "de", "7d"),
    ("Letzte 24 Stunden", "de", "1d"),
    ("Ultimi 28 giorni", "it", "28d"),
    ("365 derniers jours", "fr", "365d"),
])
def test_ranges_in_other_languages_are_recognised(pages, label, lang, expected):
    assert _period(pages, label, lang) == expected


def test_a_range_whose_words_are_not_understood_is_never_sent_as_unknown(pages):
    # A custom range prints dates. Sent with no window, it was stored as
    # today's figure; marked unrecognised, the studio refuses it as daily.
    assert _period(pages, "Oct 1, 2026 - Oct 19, 2026") == "unrecognised"


def test_a_page_with_no_range_control_still_says_so(pages):
    assert _period(pages, None) is None


# ---------------------------------------------------------------------------
# BRIDGE-15: the notice says what the studio actually did
# ---------------------------------------------------------------------------

def _notice(pages, answer, label="Past 24 hours"):
    page = pages.open("/analytics/creator/content/", analytics(label),
                      storage={"signedInVanity": "test-creator"})
    page.evaluate("(a) => { window.__answers['/api/analytics/ingest'] = a; }", answer)
    page.clock.run_for(2500)
    text = toast_text(page)
    page.context.close()
    return text or ""


def test_a_studio_that_is_not_running_is_not_reported_as_synced(pages):
    text = _notice(pages, "unreachable")
    assert "synced" not in text
    assert "could not reach your studio" in text and "not saved" in text


def test_a_studio_that_refused_this_browser_is_not_reported_as_synced(pages):
    text = _notice(pages, {"httpStatus": 401, "data": {"detail": "missing token"}})
    assert "synced" not in text
    assert "refused this browser" in text


def test_a_saved_day_draws_nothing_into_the_page(pages):
    """
    Cycle 4, decision D3: the capture confirmation lives on the action badge
    and in the side panel, from the worker's own record of the relay
    (tests/test_qc4_t1_worker_badge.py), and nothing is drawn into LinkedIn's
    page for a capture that worked. What was not saved is still said here.
    """
    text = _notice(pages, {"status": "success", "buckets_ingested": 1})
    assert text == ""


def test_a_windowed_read_says_the_follower_count_was_kept(pages):
    text = _notice(pages, {"status": "window_mismatch", "saved": 0, "followers_saved": 1, "period_label": "7d"},
                   label="Past 7 days")
    assert "7d" in text and "not saved as today's numbers" in text
    assert "follower count was saved" in text


def test_an_unrecognised_range_says_so(pages):
    text = _notice(pages, {"status": "window_mismatch", "saved": 0, "followers_saved": 0,
                           "period_label": "unrecognised"},
                   label="Oct 1, 2026 - Oct 19, 2026")
    assert "could not tell which period" in text
