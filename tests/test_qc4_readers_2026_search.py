"""
The search appearances reader on LinkedIn's 2026 page (2.10.1).
===============================================================

/me/search-appearances/ redirects to /analytics/search-appearances/, where
the owner's card (2026-10-28) reads "15 Search appearances 0% past 7 days"
(li.member-analytics-addon-summary__list-item, its label in
p.member-analytics-addon-list-item__description): the figure comes before
the label, and the window comes after the change percentage, which is never
the figure. The reader recorded no reading there. The fixtures are rebuilt
from the owner's outline with an invented count.
"""

import pytest

ME = "ada-example"
SCRIPTS = ("voyager_schema.js", "content.js", "own_pages.js", "own_insights.js")
SIGNED_IN = {"signedInVanity": ME}


@pytest.fixture(scope="module")
def pages():
    # Imported here, so a run without a browser skips these and nothing else.
    pytest.importorskip("playwright.sync_api")
    from qc_f3_pages import Pages
    p = Pages()
    yield p
    p.close()


def page_html(body, title, lang="en"):
    from qc_f3_pages import page_html as html
    return html(body, title=title, lang=lang)


def _captures(pages, page, extractor):
    return [c for c in pages.sent(page, "/api/v1/bridge/capture") if c.get("extractor") == extractor]


SEARCH = """<main><section><ul>
  <li class="member-analytics-addon-summary__list-item">
    <a><div><p><span>15</span></p><p class="member-analytics-addon-list-item__description t-14 pr3">Search appearances</p>
       <p><span><svg></svg>0%</span> past 7 days</p></div></a>
  </li></ul></section></main>"""


def test_search_appearances_take_the_figure_before_the_label_and_the_window_after_the_change(pages):
    page = pages.open("/analytics/search-appearances/", page_html(SEARCH, title="Search appearances", lang="en"),
                      scripts=SCRIPTS, storage=SIGNED_IN)
    page.clock.run_for(4000)
    sent = pages.sent(page, "/api/analytics/page-figures")
    assert [(b["page"], b["readings"]) for b in sent] == [
        ("search_appearances", [{"period_label": "7d", "precision": "exact", "figures": {"search_appearances": 15}}])]


def test_the_change_beside_the_label_is_never_the_count(pages):
    body = SEARCH.replace("<p><span>15</span></p>", "<p><span><svg></svg>12%</span></p>")
    page = pages.open("/analytics/search-appearances/", page_html(body, title="Search appearances", lang="en"),
                      scripts=SCRIPTS, storage=SIGNED_IN)
    page.clock.run_for(4000)
    assert pages.sent(page, "/api/analytics/page-figures") == []


def test_search_appearances_in_one_line_are_read_too(pages):
    body = """<main><ul><li><p>15 Search appearances <span>0%</span> past 7 days</p></li></ul></main>"""
    page = pages.open("/analytics/search-appearances/", page_html(body, title="Search appearances", lang="en"),
                      scripts=SCRIPTS, storage=SIGNED_IN)
    page.clock.run_for(4000)
    sent = pages.sent(page, "/api/analytics/page-figures")
    assert sent and sent[0]["readings"][0]["figures"] == {"search_appearances": 15}
    assert sent[0]["readings"][0]["period_label"] == "7d"
