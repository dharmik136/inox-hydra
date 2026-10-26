"""
Every reader times itself, and the capture report carries the figures.
======================================================================

Cycle 4, track 1, item 1. No reader was timed, so nothing could say whether
the bridge was smooth or which read cost the most. Each reader now wraps its
read in performance.now(); the capture report carries this run's duration,
the reads since the last report, how many of them took over 50 ms, and the
long tasks the page's timeline showed during a read. The card stamper, which
runs in the page's own world, reports through the isolated world.

These run the shipped scripts in headless Chromium (see qc_f3_pages.py). The
harness installs a fake clock, so the durations here are shapes, not
measurements; the record holds timings taken without the fake clock.
"""

import pytest

from qc_f3_pages import Pages, page_html

CAPTURE = "/api/v1/bridge/capture"
TIMING = ("duration_ms", "reads", "slow_reads", "long_tasks", "long_task_ms")


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


FEED = page_html("""
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7385000000000000001">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div class="update-components-text">Three things I learned shipping a local-first app this year.</div>
   <article class="comments-comment-item" data-id="urn:li:comment:(activity:7385000000000000001,1)">
     <a class="comments-comment-item__profile-link" href="https://www.linkedin.com/in/commenter-one/"><span>Commenter One</span></a>
     <div class="comments-comment-item__main-content">Great post.</div>
   </article>
 </div>
</main>
""", title="(3) Feed | LinkedIn")

POSTS = page_html("""
<main>
 <div id="expanded-2-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:activity:7386000000000000006">
   <div><a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a></div>
   <div data-testid="expandable-text-box">My own post about shipping a local-first app, written by me.</div>
   <button aria-label="9 reactions">9</button>
 </div>
</main>""", title="Test Creator | Activity | LinkedIn", lang="en")

ANALYTICS = page_html("<main><button class='artdeco-dropdown__trigger'>Past 24 hours</button>"
                      "<div data-test-metric-card><span data-test-metric-value>4820</span> <span>Impressions</span></div>"
                      "</main>", title="Analytics | LinkedIn", lang="en")

PROFILE = page_html("""
<main>
 <section aria-label="Primary content"><section>
   <h2>Test Creator</h2><div>Builder of local-first tools</div>
   <a href="/in/test-creator/edit/forms/intro/">Edit intro</a>
 </section></section>
</main>""", title="Test Creator | LinkedIn", lang="en")


def _reports(pages, page, extractor):
    return [c for c in pages.sent(page, CAPTURE) if c["extractor"] == extractor]


def _is_timed(report):
    for field in TIMING:
        assert field in report, f"the capture report has no {field}"
    assert isinstance(report["duration_ms"], (int, float)) and report["duration_ms"] >= 0
    assert isinstance(report["reads"], int) and report["reads"] >= 1
    assert isinstance(report["slow_reads"], int) and 0 <= report["slow_reads"] <= report["reads"]
    assert isinstance(report["long_tasks"], int) and report["long_tasks"] >= 0
    assert isinstance(report["long_task_ms"], (int, float)) and report["long_task_ms"] >= 0


def _change(page):
    page.evaluate("() => { const m = document.querySelector('main'); m.appendChild(document.createElement('span')); }")


def test_the_engagers_reader_reports_its_timing(pages):
    page = pages.open("/feed/update/urn:li:activity:7385000000000000001/", FEED)
    _change(page)
    page.clock.run_for(6000)
    reports = _reports(pages, page, "engagers")
    assert reports, "the engagers reader did not report"
    _is_timed(reports[0])


def test_the_activity_reader_reports_its_timing(pages):
    page = pages.open("/in/test-creator/recent-activity/all/", POSTS,
                      scripts=("voyager_schema.js", "content.js", "own_pages.js"))
    page.clock.run_for(4000)
    reports = _reports(pages, page, "activity_posts")
    assert reports
    _is_timed(reports[0])


def test_the_analytics_reader_reports_its_timing(pages):
    page = pages.open("/analytics/creator/content/", ANALYTICS, storage={"signedInVanity": "test-creator"})
    page.clock.run_for(3000)
    reports = _reports(pages, page, "analytics")
    assert reports
    _is_timed(reports[0])


def test_the_profile_reader_reports_its_timing(pages):
    page = pages.open("/in/test-creator/", PROFILE, scripts=("voyager_schema.js", "content.js", "own_pages.js"))
    page.clock.run_for(4000)
    reports = _reports(pages, page, "profile")
    assert reports
    _is_timed(reports[0])


def test_the_card_stamper_reports_through_the_isolated_world(pages):
    page = pages.open("/feed/", FEED, scripts=("card_urns.js", "voyager_schema.js", "content.js"))
    page.clock.run_for(2000)
    page.wait_for_timeout(50)
    reports = _reports(pages, page, "card_urns")
    assert reports, "the card stamper's run never reached the capture log"
    _is_timed(reports[0])
    assert reports[0]["items_seen"] >= 1


def test_reads_accumulate_between_throttled_reports(pages):
    """A report says how many reads it stands for, not just the last one."""
    page = pages.open("/feed/update/urn:li:activity:7385000000000000001/", FEED)
    _change(page)
    page.clock.run_for(6000)
    for _ in range(3):
        _change(page)
        page.clock.run_for(5000)
    page.clock.run_for(61000)
    _change(page)
    page.clock.run_for(5000)
    reports = _reports(pages, page, "engagers")
    assert len(reports) >= 2, "a second report never got through the throttle"
    assert reports[-1]["reads"] >= 2, "the reads between two reports were not counted"


def test_a_long_frame_that_overlaps_a_read_is_counted_against_that_reader(pages):
    """
    Long frames name the page, not the script, and carry no attribution for
    an isolated world, so the reader counts the long frames that overlapped
    its own read windows. Entries are fed by hand here, at known times.
    """
    page = pages.open("/feed/", page_html("<main></main>"))
    page.evaluate("() => { window.__t0 = performance.now(); window.__inoxReaderTiming.begin('engagers'); }")
    page.clock.run_for(20)
    took = page.evaluate("""() => {
      const t = window.__inoxReaderTiming;
      t.end('engagers');
      const start = window.__t0;
      noteLongTask({ startTime: start - 10, duration: 80 });   // overlaps the read
      noteLongTask({ startTime: start - 500, duration: 60 });  // ended before it
      return t.take('engagers');
    }""")
    assert took["long_tasks"] == 1
    assert 0 < took["long_task_ms"] <= 80
    assert took["reads"] == 1


def test_a_read_too_short_to_measure_inside_a_long_frame_still_overlaps_it(pages):
    page = pages.open("/feed/", page_html("<main></main>"))
    took = page.evaluate("""() => {
      const t = window.__inoxReaderTiming;
      const start = performance.now();
      t.begin('profile');
      t.end('profile');
      noteLongTask({ startTime: start - 10, duration: 80 });
      return t.take('profile');
    }""")
    # What is guarded is that it counts at all. The overlap is the read's own
    # length, 0 ms on an idle machine and a millisecond or two under a loaded
    # full-suite run, never the frame's 80 ms.
    assert took["long_tasks"] == 1 and 0 <= took["long_task_ms"] <= 2


def test_one_source_of_long_frames_is_observed(pages):
    """A long task sits inside a long animation frame; observing both counts one frame twice."""
    page = pages.open("/feed/", page_html("<main></main>"))
    source = page.evaluate("() => window.__inoxReaderTiming.longFrameSource()")
    supported = page.evaluate("() => PerformanceObserver.supportedEntryTypes")
    expected = "long-animation-frame" if "long-animation-frame" in supported else (
        "longtask" if "longtask" in supported else None)
    assert source == expected
