"""
The post analytics page reader: what it reads, what it marks, what it reports.
==============================================================================

Cycle 4, track 5, items 18 and 19. These run the shipped own_pages.js in
headless Chromium (see qc_f3_pages.py) on fixture post analytics pages.

The seven labels the reader has read since cycle 2 are measured. The labels
LinkedIn's Help documents beside them (followers gained from this post,
profile viewers from this post, link visits, the in-network and
out-of-network split, viewer demographics) are not verified against a 2026
page, so a page that plainly is the post analytics page and lacks one reports
it as drift rather than staying silent: Setup shows the reader as drifting
until the owner's live check settles the wording.
"""

import pytest

from qc_f3_pages import Pages, page_html

SCRIPTS = ("voyager_schema.js", "content.js", "own_pages.js")
URN = "urn:li:activity:7386000000000000501"
PATH = f"/analytics/post-summary/{URN}/"


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _read(pages, body):
    page = pages.open(PATH, page_html(body, title="Post analytics | LinkedIn", lang="en"), scripts=SCRIPTS)
    page.clock.run_for(4000)
    return page


def _card(label, figure):
    return f'<li class="card"><p class="figure">{figure}</p><p class="label">{label}</p></li>'


SEVEN = "".join(_card(label, figure) for label, figure in (
    ("Impressions", "1,912"), ("Members reached", "1,540"), ("Reactions", "57"), ("Comments", "9"),
    ("Reposts", "2"), ("Saves", "4"), ("Sends", "1")))

FOURTEEN = SEVEN + "".join(_card(label, figure) for label, figure in (
    ("Followers gained from this post", "12"), ("Profile viewers from this post", "38"), ("Link visits", "21"),
    ("Article views", "15"), ("Video views", "0"))) + """
 <section class="discovery">
   <h3>Discovery</h3>
   <div><span class="label">In your network</span><span class="share">62%</span></div>
   <div><span class="label">Outside your network</span><span class="share">38%</span></div>
 </section>
 <section class="demographics">
   <h3>Viewer demographics</h3>
   <button aria-haspopup="listbox">Job titles</button>
   <ul>
     <li><span>Founder</span><span>21%</span></li>
     <li><span>Software Engineer</span><span>14%</span></li>
     <li><span>Marketing Manager</span><span>9%</span></li>
   </ul>
 </section>"""


def _sent(pages, page):
    return pages.sent(page, "/api/v1/self/posts/analytics")


def _capture(pages, page):
    return [m["body"] for m in pages.sent(page) if m.get("path") == "/api/v1/captures"
            and m["body"].get("extractor") == "post_analytics"]


# ---------------------------------------------------------------------------
# Item 18: a rounded figure is sent as rounded
# ---------------------------------------------------------------------------

def test_a_figure_written_as_12k_is_sent_as_rounded(pages):
    page = _read(pages, f"<main><ul>{_card('Impressions', '12K')}{_card('Reactions', '57')}</ul></main>")
    sent = _sent(pages, page)
    assert sent, "nothing was sent"
    metrics = sent[0]["metrics"]
    assert metrics["impressions"] == 12000 and metrics["reactions"] == 57
    assert metrics["precision"] == "rounded"


def test_figures_written_out_in_full_are_sent_as_exact(pages):
    page = _read(pages, f"<main><ul>{SEVEN}</ul></main>")
    metrics = _sent(pages, page)[0]["metrics"]
    assert metrics["impressions"] == 1912
    assert metrics["precision"] == "exact"
