"""
The bridge's notices reach screen readers, in the side panel.
=============================================================

BRIDGE-26  Capture results ("N engagers captured", "could not reach your
           studio", the analytics refusals) appeared only visually, for 3.5 s,
           in an element with no role. They became a status (an alert for a
           warning) drawn into LinkedIn's page, built as text.

Cycle 4 (decision D3, review finding S7) moved them off LinkedIn's page. The
page gives the worker the sentence, as text; the side panel shows it at its
top in a status line that screen readers announce, as text, so a name or a
studio reason is never read as markup. Nothing is drawn into the page.
"""

import pytest

from qc_f3_pages import Pages, notice_text, page_html


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


REASON = "Inox Hydra: the studio did not save these analytics: <b>x</b>."


def test_a_notice_leaves_the_page_as_text_and_draws_nothing(pages):
    page = pages.open("/feed/", page_html("<main></main>"))
    before = page.evaluate("() => document.body.innerHTML")
    page.evaluate("(m) => noticeToPanel(m, 'warning')", REASON)
    page.clock.run_for(100)
    assert notice_text(page) == REASON
    assert page.evaluate("() => document.body.innerHTML") == before, "a notice was drawn into LinkedIn's page"


def test_the_panel_says_it_in_a_status_line_as_text(pages):
    from test_qc4_t1_panel_from_storage import NOTICE, PANEL, _open
    page = _open(pages, PANEL, "sidepanel.js", {}, session={"pageNotice": {**NOTICE, "message": REASON}})
    line = page.evaluate("""() => { const e = document.getElementById('sp-page-notice');
      return { role: e.getAttribute('role'), live: e.getAttribute('aria-live'), bold: !!e.querySelector('b'),
               text: e.textContent, hidden: e.hidden }; }""")
    assert line["role"] == "status" and line["live"] == "polite"
    assert line["bold"] is False and "<b>x</b>" in line["text"]
    assert line["hidden"] is False
