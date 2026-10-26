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
    """The capture log entries the reader sent, oldest first; drift is null on a clean read."""
    return [m["body"] for m in pages.sent(page) if m.get("path") == "/api/v1/bridge/capture"
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
# ---------------------------------------------------------------------------
# Item 19: the fourteen figures, the percentage split and demographics
# ---------------------------------------------------------------------------

def test_the_seven_new_labels_are_read_from_the_page(pages):
    page = _read(pages, f"<main><ul>{FOURTEEN}</ul></main>")
    metrics = _sent(pages, page)[0]["metrics"]
    assert metrics["followers_gained"] == 12
    assert metrics["profile_viewers"] == 38
    assert metrics["link_visits"] == 21
    assert metrics["article_views"] == 15
    assert metrics["video_views"] == 0
    assert metrics["in_network_pct"] == 62 and metrics["out_of_network_pct"] == 38
    assert metrics["demographics"] == [
        {"dimension": "job_title", "label": "Founder", "percentage": 21},
        {"dimension": "job_title", "label": "Software Engineer", "percentage": 14},
        {"dimension": "job_title", "label": "Marketing Manager", "percentage": 9},
    ]
    capture = _capture(pages, page)[-1]
    assert not capture["drift"], "every label was found, so nothing drifted"
    assert capture["items_seen"] == 14


def test_a_percentage_is_never_read_as_a_count(pages):
    """NUMBER_ONLY refuses "62%", so the split cannot land in members reached."""
    body = """<main><ul>
      <li><p class="label">Members reached</p><p>62%</p><p>2,900</p></li>
      <li><p class="label">Impressions</p><p>4,100</p></li>
    </ul></main>"""
    page = _read(pages, body)
    metrics = _sent(pages, page)[0]["metrics"]
    assert metrics["members_reached"] == 2900 and metrics["impressions"] == 4100


def test_an_absent_unverified_label_is_drift_not_silence(pages):
    """
    The page plainly is the post analytics page (the seven measured labels
    are there), so each documented label it lacks is reported, by name.
    """
    page = _read(pages, f"<main><ul>{SEVEN}</ul></main>")
    capture = _capture(pages, page)[-1]
    assert capture["items_seen"] == 7
    assert set(capture["drift"]) == {"followers_gained", "profile_viewers", "in_network_pct", "out_of_network_pct",
                                     "demographics"}
    metrics = _sent(pages, page)[0]["metrics"]
    assert "link_visits" not in metrics and "demographics" not in metrics, "a figure not on the page is not sent"


def test_content_specific_labels_are_not_drift_when_absent(pages):
    """A text post has no link visits, article views or video views; their absence says nothing."""
    page = _read(pages, f"<main><ul>{SEVEN}</ul></main>")
    assert not {"link_visits", "article_views", "video_views"} & set(_capture(pages, page)[-1]["drift"] or [])


def test_a_page_with_no_labels_at_all_reports_only_the_labels(pages):
    """Not the post analytics page as the reader knows it: the one drift it always reported, nothing sent."""
    page = _read(pages, "<main><p>Something else entirely</p></main>")
    assert _capture(pages, page)[-1]["drift"] == ["metric_labels"]
    assert _sent(pages, page) == []


def test_a_demographics_heading_with_no_readable_entries_is_drift(pages):
    body = f"<main><ul>{SEVEN}</ul><section><h3>Viewer demographics</h3><p>Not enough data yet</p></section></main>"
    page = _read(pages, body)
    assert "demographics_entries" in _capture(pages, page)[-1]["drift"]
