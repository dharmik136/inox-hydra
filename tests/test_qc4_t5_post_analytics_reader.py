"""
The post analytics page reader: what it reads, what it marks, what it reports.
==============================================================================

Cycle 4, track 5, items 18 and 19. These run the shipped own_pages.js in
headless Chromium (see qc_f3_pages.py) on fixture post analytics pages.

The seven labels the reader has read since cycle 2 are measured, and only
they can report drift. The labels LinkedIn's Help documents beside them
(followers gained from this post, profile viewers from this post, link
visits, the content-specific figures, the in-network and out-of-network
split, viewer demographics) are not verified against a 2026 page, and by the
owner's decision of 2026-10-26 an absent one is not drift: LinkedIn may not
show those figures to every member or on every post. Nothing is sent for an
absent one, and the studio derives from its readings how long each has gone
unread (tests/test_qc4_t5_derive.py).
"""

import os
import sys

import pytest

from qc_f3_pages import Pages, page_html

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "studio", "backend"))

SCRIPTS = ("content.js", "own_pages.js")
NEW_FIELDS = {"followers_gained", "profile_viewers", "link_visits", "article_views", "video_views",
              "in_network_pct", "out_of_network_pct", "demographics"}
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


def test_a_page_missing_every_new_label_is_read_with_no_drift(pages, monkeypatch, tmp_path):
    """
    The owner's decision of 2026-10-26: a label added this cycle that is
    absent is not drift. A page carrying only the seven verified labels is
    read in full, sends nothing for the others, never a 0, and leaves the
    reader working.
    """
    page = _read(pages, f"<main><ul>{SEVEN}</ul></main>")
    capture = _capture(pages, page)[-1]
    assert capture["items_seen"] == 7 and not capture["drift"]
    assert not NEW_FIELDS & set(_sent(pages, page)[0]["metrics"]), "an absent figure is not sent"
    # The studio's own reading of that capture: the reader is working.
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    from database import init_db
    import onboarding
    init_db()
    onboarding.record_capture(capture)
    health = {h["extractor"]: h for h in onboarding.capture_health()}
    assert health["post_analytics"]["state"] == "working" and health["post_analytics"]["drift"] == []


def test_a_page_missing_a_verified_label_still_reports_drift(pages):
    """Saves is one of the seven read since cycle 2: missing beside the other six, it is a changed label."""
    six = "".join(_card(label, figure) for label, figure in (
        ("Impressions", "1,912"), ("Members reached", "1,540"), ("Reactions", "57"), ("Comments", "9"),
        ("Reposts", "2"), ("Sends", "1"), ("Followers gained from this post", "12")))
    page = _read(pages, f"<main><ul>{six}</ul></main>")
    assert _capture(pages, page)[-1]["drift"] == ["saves"]


def test_a_page_with_no_labels_at_all_reports_only_the_labels(pages):
    """Not the post analytics page as the reader knows it: the one drift it always reported, nothing sent."""
    page = _read(pages, "<main><p>Something else entirely</p></main>")
    assert _capture(pages, page)[-1]["drift"] == ["metric_labels"]
    assert _sent(pages, page) == []


def test_a_demographics_heading_with_no_readable_entries_stores_nothing_and_is_not_drift(pages):
    """LinkedIn may hold demographics back on a post with few viewers: nothing to store, and not drift."""
    body = f"<main><ul>{SEVEN}</ul><section><h3>Viewer demographics</h3><p>Not enough data yet</p></section></main>"
    page = _read(pages, body)
    assert not _capture(pages, page)[-1]["drift"]
    assert "demographics" not in _sent(pages, page)[0]["metrics"]


# ---------------------------------------------------------------------------
# Telling the split and the demographics apart from what sits near them
# ---------------------------------------------------------------------------

def test_a_network_split_that_does_not_add_up_is_dropped_and_is_not_drift(pages):
    """
    The two shares are complementary. In a column layout both labels can
    find the same percentage first; 62 and 62 is a misread, not a figure.
    A new field that fails its own check is dropped, and is not drift
    (owner, 2026-10-26).
    """
    body = f"""<main><ul>{SEVEN}</ul>
      <section><div><span>In your network</span><span>Outside your network</span></div>
               <div><span>62%</span><span>38%</span></div></section></main>"""
    page = _read(pages, body)
    metrics = _sent(pages, page)[0]["metrics"]
    assert "in_network_pct" not in metrics and "out_of_network_pct" not in metrics
    assert not _capture(pages, page)[-1]["drift"]


def test_demographics_never_take_the_network_split_above_their_heading(pages):
    body = f"""<main><ul>{SEVEN}</ul>
      <section><div><span>In your network</span><span>62%</span></div>
               <div><span>Outside your network</span><span>38%</span></div>
               <h3>Viewer demographics</h3>
               <ul><li><span>Founder</span><span>21%</span></li><li><span>Engineer</span><span>14%</span></li></ul>
      </section></main>"""
    page = _read(pages, body)
    metrics = _sent(pages, page)[0]["metrics"]
    assert (metrics["in_network_pct"], metrics["out_of_network_pct"]) == (62, 38)
    labels = [entry["label"] for entry in metrics["demographics"]]
    assert labels == ["Founder", "Engineer"], labels


# ---------------------------------------------------------------------------
# Review S1: an entry is bound by its own element, never by page order
# ---------------------------------------------------------------------------

def _demographics(pages, body):
    page = _read(pages, f"<main><ul>{SEVEN}</ul>{body}</main>")
    capture = _capture(pages, page)[-1]
    assert not capture["drift"], "demographics are never drift"
    return _sent(pages, page)[0]["metrics"].get("demographics")


def test_demographics_with_the_percentage_before_the_label_are_bound_by_their_row(pages):
    """The reviewer's probe B: by page order every entry was shifted by one and the last was lost."""
    entries = _demographics(pages, """<section><h3>Viewer demographics</h3><button>Job titles</button><ul>
        <li><span>21%</span><span>Founder</span></li>
        <li><span>14%</span><span>Software Engineer</span></li>
        <li><span>9%</span><span>Marketing Manager</span></li></ul></section>""")
    assert entries == [
        {"dimension": "job_title", "label": "Founder", "percentage": 21},
        {"dimension": "job_title", "label": "Software Engineer", "percentage": 14},
        {"dimension": "job_title", "label": "Marketing Manager", "percentage": 9},
    ]


def test_demographics_listed_category_by_category_take_each_entrys_own_heading(pages):
    """The reviewer's probe C: Berlin and London were filed as job titles."""
    entries = _demographics(pages, """<section><h3>Viewer demographics</h3>
        <h4>Job titles</h4><ul><li><span>Founder</span><span>21%</span></li></ul>
        <h4>Locations</h4><ul><li><span>Berlin</span><span>30%</span></li><li><span>London</span><span>20%</span></li></ul>
      </section>""")
    assert [(e["dimension"], e["label"]) for e in entries] == [
        ("job_title", "Founder"), ("location", "Berlin"), ("location", "London")]


def test_a_tab_bar_of_categories_leaves_the_category_unknown(pages):
    """Every category named before the entries says nothing about which one they are."""
    entries = _demographics(pages, """<section><h3>Viewer demographics</h3>
        <div><button>Job titles</button><button>Locations</button><button>Industries</button></div>
        <ul><li><span>Berlin</span><span>30%</span></li><li><span>London</span><span>20%</span></li></ul></section>""")
    assert {e["dimension"] for e in entries} == {"unknown"}


def test_a_demographics_word_above_the_network_split_never_files_the_split_as_demographics(pages):
    """The reviewer's probe D: a tab or summary line saying Demographics above the discovery block."""
    page = _read(pages, f"""<main><nav><a>Demographics</a></nav><ul>{SEVEN}</ul>
      <section><div><span>In your network</span><span>62%</span></div>
               <div><span>Outside your network</span><span>38%</span></div></section>
      <section><ul><li><span>Founder</span><span>21%</span></li><li><span>Engineer</span><span>14%</span></li></ul></section>
    </main>""")
    metrics = _sent(pages, page)[0]["metrics"]
    assert (metrics["in_network_pct"], metrics["out_of_network_pct"]) == (62, 38)
    labels = [e["label"] for e in metrics.get("demographics", [])]
    assert labels == ["Founder", "Engineer"], labels


def test_demographics_that_cannot_be_bound_store_nothing(pages):
    """Labels and percentages as loose siblings: no element binds one to the other, so nothing is kept."""
    entries = _demographics(pages, """<section><h3>Viewer demographics</h3>
        <p>Founder</p><p>21%</p><p>Software Engineer</p><p>14%</p></section>""")
    assert entries is None
