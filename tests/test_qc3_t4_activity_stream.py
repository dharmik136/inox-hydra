"""
The activity stream is read once for a visit.
=============================================

Cycle 3, batch T4, and ONEVIEW section 1.3: Activity spent 118 KB over five
seconds from navigation, of which /api/v1/self/activity-stream was 56 KB
"fetched twice". Measured here with the page's clock held still, the screen
reads the stream once when it opens: the second read in that five second
window is the Activity screen's own auto refresh, which reads every 2.5
seconds while the window is in view and which the creator can turn off on the
screen (tests/test_qc2_r5_refresh.py holds that behaviour). So there is no
duplicate read to remove, and this pins it that way, because a screen that
starts reading twice is invisible until someone counts.

The second test holds the size of one read, so the answer the poll re-sends
cannot quietly grow past the section bar.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401,E402

STREAM = "/api/v1/self/activity-stream"


def test_the_activity_screen_reads_the_stream_once_for_one_visit(studio):
    """A visit, with the clock held still so the auto refresh cannot fire."""
    page = studio["page"]
    seed_creator(studio["client"])
    page.clock.install()
    reads = []
    page.on("request", lambda request: STREAM in request.url and reads.append(request.url))
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")
    page.wait_for_timeout(300)
    assert len(reads) == 1, f"the activity stream was read {len(reads)} times for one visit: {reads}"


def test_one_read_of_the_stream_stays_under_the_section_bar(studio):
    """56 KB on three years of one creator, at the 50 rows per list the screen asks for."""
    seed_creator(studio["client"])
    answer = studio["client"].get(f"{STREAM}?limit=50")
    assert answer.status_code == 200, answer.text
    assert len(answer.content) < 150 * 1024, f"one read of the stream is {len(answer.content) / 1024:.0f} KB"
    assert set(answer.json()) >= {"summary", "recent_posts", "recent_comments", "recent_reactions",
                                 "recent_leads", "recent_imports"}
