"""
The new sections answer their first-view question inside the first viewport.
============================================================================

Cycle 4, track 4. The sections report asks, for each new section, whether its
first view answers its question at desktop width without scrolling, under
the Cycle 3 bar: no more than two scroll pages, the work area used, and the
things that answer the question on screen at 1440x900 before any scroll.

These drive the built interface the way tests/test_qc3_t5_today_command_centre.py
does, on a throwaway home seeded through the routes the extension calls.
Each measurement is also printed so the record can quote it.

Strict Invariants:
- Zero em-dashes.
"""

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import ME, confirm_identity, open_section, seed_creator, server, studio  # noqa: F401

VIEWPORT_HEIGHT = 900


def _inside_first_viewport(page, selector):
    """Whether the first element matching `selector` ends above the fold."""
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"{selector} is not drawn"
    return box["y"] + box["height"] <= VIEWPORT_HEIGHT


def _measure(page):
    """Scroll pages of the work area, and the share of its width that carries text."""
    return page.evaluate("""() => {
      const main = document.querySelector('main');
      const box = main.getBoundingClientRect();
      let left = Infinity, right = 0, ink = 0;
      for (const el of main.querySelectorAll('*')) {
        if (!el.textContent || !el.textContent.trim() || el.children.length) continue;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0 || r.top > window.innerHeight) continue;
        left = Math.min(left, r.left); right = Math.max(right, r.right);
        ink += Math.min(r.width, box.width) * Math.min(r.height, window.innerHeight - Math.max(r.top, 0));
      }
      return {
        pages: main.scrollHeight / main.clientHeight,
        used: (right - left) / box.width,
        ink: ink / (box.width * Math.min(box.height, window.innerHeight)),
      };
    }""")


def _capture(client, extractor, items_seen=4, items_kept=3, drift=None):
    payload = {"extractor": extractor, "items_seen": items_seen, "items_kept": items_kept,
               "page_kind": "own_post", "extension_version": "2.7.0"}
    if drift:
        payload["drift"] = drift
    from security import TOKEN_HEADER, get_or_create_token
    answer = client.post("/api/v1/bridge/capture", json=payload, headers={TOKEN_HEADER: get_or_create_token()})
    assert answer.status_code == 200, answer.text


# ---------------------------------------------------------------------------
# Health: is the bridge reading, what did each reader read in the last seven
# days, and what could it not read?
# ---------------------------------------------------------------------------

def test_health_answers_whether_the_bridge_is_reading_in_the_first_viewport(studio):
    client = studio["client"]
    seed_creator(client)
    _capture(client, "engagers")
    _capture(client, "profile", items_seen=1, items_kept=1)
    _capture(client, "activity_posts", items_seen=3, items_kept=0, drift=["post_text"])

    page = open_section(studio, "health")
    expect(page.locator("h1")).to_have_text("Is the bridge reading?")
    main = page.locator("main")
    expect(main).to_contain_text("Readers, last 7 days", timeout=10000)
    expect(main).to_contain_text("WORKING")
    expect(main).to_contain_text("CANNOT READ POST TEXT")
    expect(main).to_contain_text("NOT SEEN YET")
    expect(main).to_contain_text("since the studio started")
    expect(main).to_contain_text("not reported by this extension version")

    # The question is answered above the fold: the bridge line, the four
    # figures and the whole readers table are inside the first viewport.
    assert _inside_first_viewport(page, "main header")
    assert _inside_first_viewport(page, "main dl")
    assert _inside_first_viewport(page, "main table")
    assert page.locator("h1:visible").count() == 1

    measured = _measure(page)
    print(f"\nHealth at 1440x900: {measured['pages']:.2f} scroll pages, {measured['used']:.0%} of the width used, "
          f"{measured['ink']:.0%} ink in the first viewport")
    assert measured["pages"] <= 2.0, f"Health is {measured['pages']:.2f} screens tall"
    assert measured["used"] > 0.9
    assert studio["errors"] == [], studio["errors"]


def test_health_opens_a_readers_runs_one_level_down(studio):
    client = studio["client"]
    seed_creator(client)
    _capture(client, "engagers", items_seen=7, items_kept=5)
    page = open_section(studio, "health")
    page.get_by_role("button", name="Comments and reactions on your posts").click()
    main = page.locator("main")
    expect(main).to_contain_text("seen 7, kept 5", timeout=5000)
    expect(main).to_contain_text("BY DAY, KEPT")
    assert studio["errors"] == [], studio["errors"]


def test_health_offers_the_update_check_off_by_default(studio):
    seed_creator(studio["client"])
    page = open_section(studio, "health")
    box = page.get_by_role("checkbox", name="Check GitHub for a newer version")
    expect(box).not_to_be_checked()
    expect(page.locator("main")).to_contain_text("no request leaves this machine")
    assert page.get_by_role("button", name="Check now").count() == 0, "Check now is offered before consent"
