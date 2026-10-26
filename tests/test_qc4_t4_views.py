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
    """
    The Cycle 3 one-view figures (its research, ONEVIEW section 1.1): scroll
    pages are scrollHeight / clientHeight of the scrolling region; ink is the
    share of the viewport covered by visible text, on an 8 pixel grid over
    every rendered text box inside <main>, with screen reader only and
    aria-hidden text left out. "used" is how much of the work area's width
    the text spans.
    """
    return page.evaluate("""() => {
      const main = document.querySelector('main');
      const box = main.getBoundingClientRect();
      const W = window.innerWidth, H = window.innerHeight, G = 8;
      const cols = Math.ceil(W / G), rows = Math.ceil(H / G);
      const covered = new Uint8Array(cols * rows);
      let left = Infinity, right = 0;
      const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if (!node.textContent.trim()) continue;
        const el = node.parentElement;
        if (!el || el.closest('[aria-hidden="true"], .sr-only')) continue;
        const style = getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const r of range.getClientRects()) {
          if (r.width <= 0 || r.height <= 0 || r.right <= 0 || r.bottom <= 0 || r.left >= W || r.top >= H) continue;
          left = Math.min(left, r.left); right = Math.max(right, r.right);
          const x0 = Math.max(0, Math.floor(r.left / G)), x1 = Math.min(cols - 1, Math.floor((r.right - 0.01) / G));
          const y0 = Math.max(0, Math.floor(r.top / G)), y1 = Math.min(rows - 1, Math.floor((r.bottom - 0.01) / G));
          for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) covered[y * cols + x] = 1;
        }
      }
      let inked = 0;
      for (const cell of covered) inked += cell;
      return {
        pages: main.scrollHeight / main.clientHeight,
        used: (right - left) / box.width,
        ink: inked / covered.length,
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


# ---------------------------------------------------------------------------
# Replies: who commented on my posts that I have not answered, oldest-seen
# first?
# ---------------------------------------------------------------------------

COMMENTERS = (
    ("Lena Fischer", "lena-fischer-x", 0, "We moved our rota into the repo last spring and never looked back."),
    ("Omar Haddad", "omar-haddad-x", 1, "Which spreadsheet was it? Asking for a friend who owns three."),
    ("Ines Duarte", "ines-duarte-x", 1, "The bit about handoffs is the part nobody budgets for."),
    ("Kofi Mensah", "kofi-mensah-x", 2, "A third is a big number. What did you stop doing?"),
)


def _seed_comments(client, urns):
    for name, vanity, post, text in COMMENTERS:
        answer = client.post("/api/v1/crm/interactions/ingest", json={
            "full_name": name, "profile_url": f"https://www.linkedin.com/in/{vanity}",
            "headline": f"Engineering at {name.split()[1]} and Co", "company": "Co", "interaction_type": "COMMENT",
            "comment_text": text, "post_urn": urns[post], "post_author": ME,
        })
        assert answer.status_code == 200, answer.text


def test_replies_answers_who_is_waiting_in_the_first_viewport(studio):
    client = studio["client"]
    urns = seed_creator(client, commenter="Anika Shah", comment="This matches what we saw last year.")
    _seed_comments(client, urns)

    page = open_section(studio, "replies")
    expect(page.locator("h1")).to_have_text("Who is waiting on a reply")
    main = page.locator("main")
    expect(main).to_contain_text("This matches what we saw last year.", timeout=10000)
    expect(main).to_contain_text("SEEN BY THE STUDIO")
    expect(main).to_contain_text("COMMENTS WAITING, LAST 14 DAYS")
    for name, _vanity, _post, text in COMMENTERS:
        expect(main).to_contain_text(name)
    assert page.locator("main section").count() == 3, "the comments are not grouped by post"
    assert page.locator("h1:visible").count() == 1

    # The question is answered above the fold: the figures and the first
    # post's waiting comments.
    assert _inside_first_viewport(page, "main dl")
    assert _inside_first_viewport(page, "main section")

    measured = _measure(page)
    print(f"\nReplies at 1440x900: {measured['pages']:.2f} scroll pages, {measured['used']:.0%} of the width used, "
          f"{measured['ink']:.0%} ink in the first viewport")
    assert measured["pages"] <= 2.0, f"Replies is {measured['pages']:.2f} screens tall"
    assert measured["used"] > 0.9
    assert studio["errors"] == [], studio["errors"]


def test_marking_a_reply_answered_empties_the_list_and_says_how_many_were_answered(studio):
    client = studio["client"]
    seed_creator(client, commenter="Anika Shah", comment="This matches what we saw last year.")
    page = open_section(studio, "replies")
    main = page.locator("main")
    expect(main).to_contain_text("This matches what we saw last year.", timeout=10000)
    page.get_by_role("button", name="Answered, Anika Shah's comment").click()
    expect(main).to_contain_text("Nobody from the last 14 days is waiting on a reply.", timeout=5000)
    expect(main).to_contain_text("You marked 1 answered in the last 7 days.")
    expect(page.get_by_role("button", name="Undo")).to_be_visible()

    page.get_by_role("button", name="Undo").click()
    expect(main).to_contain_text("This matches what we saw last year.", timeout=5000)
    assert studio["errors"] == [], studio["errors"]


def test_today_counts_the_comments_waiting_and_opens_replies(studio):
    client = studio["client"]
    urns = seed_creator(client, commenter="Anika Shah", comment="This matches what we saw last year.")
    _seed_comments(client, urns)
    page = open_section(studio, "today")
    link = page.get_by_role("button", name="5 COMMENTS WAITING, OPEN REPLIES")
    expect(link).to_be_visible(timeout=10000)
    link.click()
    expect(page.locator("h1")).to_have_text("Who is waiting on a reply", timeout=5000)
    assert studio["errors"] == [], studio["errors"]
