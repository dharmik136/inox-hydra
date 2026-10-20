"""
Screens that come back with the studio, and stay current while open.
===================================================================

Cycle 2, batch R5, D-14 and D-26. A screen that failed while the studio was
down kept "could not be read" after it returned, although the banner above it
said that line would go away by itself. Queue, Leads and Posts read once when
opened, so a post that came due or a person captured from the other window
appeared only after moving away and back. Activity read every 2.5 seconds for
as long as it was open, hidden tab or not.

The outage is made by refusing every /api request in the page, which is how
the window sees a stopped studio: a request that cannot reach it.
"""

import re

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: F401

# Lets a test say the window is hidden. Headless Chromium always reports
# "visible", and the screens decide whether to poll from this.
VISIBILITY = """
Object.defineProperty(Document.prototype, "visibilityState", {
  configurable: true,
  get() { return window.__visibility || "visible"; },
});
"""


def _studio_down(page):
    page.route(re.compile(r".*/api/.*"), lambda route: route.abort())


def _studio_back(page):
    page.unroute(re.compile(r".*/api/.*"))


def test_brand_studio_recovers_by_itself_when_the_studio_returns(studio):
    page = studio["page"]
    _studio_down(page)
    page.goto(studio["url"] + "/#/settings")
    page.wait_for_selector("text=THE PROFILE COULD NOT BE READ.")
    page.wait_for_selector("text=The studio is not answering")
    _studio_back(page)
    # The banner asks again every five seconds; the screen follows it.
    page.wait_for_selector("h1:has-text('Brand Studio')", timeout=12000)
    assert page.locator("text=THE PROFILE COULD NOT BE READ.").count() == 0


def test_posts_recover_by_themselves_when_the_studio_returns(studio):
    seed_creator(studio["client"])
    page = studio["page"]
    _studio_down(page)
    page.goto(studio["url"] + "/#/posts")
    page.wait_for_selector("text=POSTS ARE UNAVAILABLE")
    _studio_back(page)
    page.wait_for_selector("text=Your on-call rota is a culture document.", timeout=12000)


def test_posts_read_again_on_coming_back_to_the_window(studio):
    page = studio["page"]
    page.clock.install()
    open_section(studio, "posts")
    page.wait_for_selector("text=None of your posts have been imported yet")
    # The bridge captures from the other window while this one is open.
    seed_creator(studio["client"], commenter=None)
    page.clock.fast_forward("00:20")
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.wait_for_selector("text=Your on-call rota is a culture document.", timeout=5000)


def test_leads_read_again_on_coming_back_to_the_window(studio):
    page = studio["page"]
    page.clock.install()
    seed_creator(studio["client"])
    open_section(studio, "leads")
    page.get_by_role("button", name="Anika Shah").first.wait_for()
    studio["client"].post("/api/v1/crm/interactions/ingest", json={
        "full_name": "Kenji Sato", "profile_url": "https://www.linkedin.com/in/kenji-sato-x",
        "headline": "Staff Engineer at Routely", "company": "Routely", "interaction_type": "COMMENT",
        "comment_text": "We did the same with our pager.", "post_author": "priya-raman-r5",
    })
    page.clock.fast_forward("00:20")
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    page.get_by_role("button", name="Kenji Sato").first.wait_for(timeout=5000)


def test_the_queue_reads_again_while_open(studio):
    page = studio["page"]
    page.clock.install()
    reads = []
    page.on("request", lambda request: "/api/queue/smart-slots" in request.url and reads.append(request.url))
    open_section(studio, "queue")
    before = len(reads)
    page.clock.run_for("01:05")
    page.wait_for_timeout(300)
    assert len(reads) - before >= 2, f"the Queue read {len(reads) - before} times in 65 seconds"


def test_activity_does_not_poll_a_hidden_window(studio):
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    page.clock.install()
    reads = []
    page.on("request", lambda request: "/api/v1/self/activity-stream" in request.url and reads.append(request.url))
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")

    page.evaluate("window.__visibility = 'visible'")
    start = len(reads)
    page.clock.run_for("00:10")
    page.wait_for_timeout(300)
    visible = len(reads) - start
    assert visible >= 3, f"Activity read {visible} times in 10 visible seconds"

    page.evaluate("window.__visibility = 'hidden'")
    start = len(reads)
    page.clock.run_for("01:00")
    page.wait_for_timeout(300)
    assert len(reads) - start == 0, f"Activity read {len(reads) - start} times in a hidden minute"
