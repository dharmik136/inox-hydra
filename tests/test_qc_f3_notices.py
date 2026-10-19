"""
The bridge's notices on LinkedIn reach screen readers.
======================================================

BRIDGE-26  Capture results ("N engagers captured", "could not reach your
           studio", the analytics refusals) appeared only visually, for 3.5 s,
           in an element with no role. They are now a status (an alert for a
           warning), stay at least 6 s, and are built as text, so a name or a
           studio reason is never read as markup.
"""

import pytest

from qc_f3_pages import Pages, page_html


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


TOAST = "() => { const t = document.getElementById('studio-bridge-inpage-toast'); return t ? {role: t.getAttribute('role'), live: t.getAttribute('aria-live'), text: t.innerText, bold: !!t.querySelector('b')} : null; }"


def test_a_success_notice_is_a_status(pages):
    page = pages.open("/feed/", page_html("<main></main>"))
    page.evaluate("() => showInPageToast('Inox Hydra: 2 engager(s) on your post captured.', 'success')")
    toast = page.evaluate(TOAST)
    assert toast["role"] == "status" and toast["live"] == "polite"
    assert "2 engager(s) on your post captured." in toast["text"]


def test_a_warning_is_an_alert_shown_as_text_for_six_seconds(pages):
    page = pages.open("/feed/", page_html("<main></main>"))
    page.evaluate("() => showInPageToast('Inox Hydra: the studio did not save these analytics: <b>x</b>.', 'warning')")
    toast = page.evaluate(TOAST)
    assert toast["role"] == "alert" and toast["live"] == "assertive"
    assert toast["bold"] is False and "<b>x</b>" in toast["text"]
    page.clock.run_for(5900)
    assert page.evaluate(TOAST) is not None
    page.clock.run_for(1000)
    assert page.evaluate(TOAST) is None
