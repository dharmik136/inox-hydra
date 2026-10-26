"""
From your record, driven in the built interface.
================================================

Cycle 4, track 7, batch 4 of the personalised daily ideas report, against
the built interface (tests/qc2_r5_live.py) at the 1440x900 the section bar
is set at: the day's cards in one view, a keep that reaches Kept, an ask
that reaches What the studio knows, nothing leaving loopback, and no
sideways scroll on a phone. Invented people and posts only.
"""

import os
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from qc2_r5_live import ME, open_section, seed_creator, server, studio, urn_days_ago  # noqa: F401,E402


def seed_record(client):
    """A creator who finished Setup, with comments of their own and an ask, and today's batch built."""
    seed_creator(client)
    items = [{"target_activity_urn": urn_days_ago(3 + i, 700 + i), "kind": "comment",
              "my_text": f"We tried the same with our dispatch rota, and the {['first', 'second', 'third'][i]} week was the hard one.",
              "target_author": f"Somebody Else {i}", "target_excerpt": "Their post, which no card shows."}
             for i in range(3)]
    assert client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": items}).status_code == 200
    assert client.post("/api/v1/record/asks", json={"text": "queues and on-call rotas", "source": "ask_box"}).status_code == 200
    import record_daily

    assert record_daily.run_today()["status"] in ("built", "carried")


def test_the_days_cards_are_one_view_with_their_labels(studio):
    client, page = studio["client"], studio["page"]
    seed_record(client)
    egress = []
    page.on("request", lambda request: None if request.url.startswith(("http://127.0.0.1", "data:", "blob:"))
            else egress.append(request.url))
    open_section(studio, "record")
    expect(page.locator("h1")).to_have_text("What is worth writing from today")
    main = page.locator("main")
    expect(main).to_contain_text("COMPUTED TODAY AT", timeout=10000)
    for block in ("Working for you", "You asked", "You engaged with"):
        expect(main).to_contain_text(block)
    # The other person's words never reach the screen.
    assert "Somebody Else" not in main.inner_text()
    assert "which no card shows" not in main.inner_text()
    pages = page.evaluate("() => { const m = document.querySelector('main'); return m.scrollHeight / m.clientHeight; }")
    assert pages <= 2.0, f"the section is {pages:.2f} screens tall"
    assert egress == [], egress
    assert studio["errors"] == [], studio["errors"]


def test_a_keep_reaches_the_kept_level(studio):
    client, page = studio["client"], studio["page"]
    seed_record(client)
    open_section(studio, "record")
    keepable = page.locator("main article").filter(has=page.get_by_role("button", name="Keep", exact=True)).first
    expect(keepable).to_be_visible(timeout=10000)
    # Pinned by its name, which a keep does not change: the filter above stops matching once it is kept.
    card = page.get_by_role("article", name=keepable.get_attribute("aria-label"), exact=True)
    card.get_by_role("button", name="Keep", exact=True).click()
    expect(card.get_by_role("button", name="Kept", exact=True)).to_be_visible(timeout=10000)
    page.get_by_role("button", name="Kept", exact=True).first.click()
    expect(page.locator("main")).to_contain_text("Every card you kept", timeout=10000)
    expect(page.locator("main article").first).to_be_visible()
    assert studio["errors"] == [], studio["errors"]


def test_an_ask_typed_in_the_box_is_on_what_the_studio_knows(studio):
    client, page = studio["client"], studio["page"]
    seed_record(client)
    open_section(studio, "record")
    page.get_by_label("Ask for something to write about").first.fill("pricing for a two person studio")
    page.get_by_role("button", name="Remember this ask").click()
    expect(page.locator("main")).to_contain_text("Remembered.", timeout=10000)
    page.get_by_role("button", name="What the studio knows").click()
    expect(page.locator("main")).to_contain_text("pricing for a two person studio", timeout=10000)
    expect(page.locator("main")).to_contain_text("in the ask box")
    assert studio["errors"] == [], studio["errors"]


def test_no_sideways_scroll_on_a_phone(studio):
    client = studio["client"]
    seed_record(client)
    context = studio["page"].context.browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
    try:
        page = context.new_page()
        page.goto(studio["url"] + "/#/record", wait_until="networkidle")
        expect(page.locator("h1")).to_have_text("What is worth writing from today")
        overflow = page.evaluate("() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)")
        assert overflow == 0, f"the section scrolls sideways by {overflow}px on a phone"
    finally:
        context.close()
