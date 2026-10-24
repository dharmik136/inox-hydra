"""
The three screens of batch T6, driven in a browser.
===================================================

Cycle 3, batch T6. What the creator can actually do on Posts, Analytics and
Patterns, read from the built interface rather than from the source:

- Posts prints how many posts it is showing of how many there are, and the
  control beside that count reaches the rest. The screen showed 50 of 1,417
  with nothing past the fiftieth row.
- A row opens one post into its detail, with the whole post in it, and
  Escape closes it again.
- The search box and the settle filter move the count, so the pager cannot
  walk past the end of what they left.
- Analytics prints no percentage over 100, and pages its comparison table.
- Patterns has more than the two controls it had.

Every context blocks service workers: the studio's worker answers requests
from its own cache, which hides them from the test and from page.route.
"""

import os
import re
import shutil
import socket as _socket
import sys
import tempfile
import threading
import time
import types

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

# This file imports the app in process, which the brief allows only behind the
# sandbox's socket guard. tests/conftest.py already installs that guard for the
# whole session, host for host, and records what it refused
# (test_qc2_r2_network_guard.py reads those records), so this file installs
# nothing of its own: a second copy wrapping the first swallows the refusal
# before conftest can write it down.
_real_create = _socket.create_connection

import qc2_r3_data  # noqa: E402

BUILT = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
pytestmark = pytest.mark.skipif(not os.path.exists(BUILT),
                                reason="the interface is not built (npm --prefix studio/ui run build)")


def _free_port() -> int:
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="module")
def studio():
    """The studio on its own port, over a seeded creator history."""
    import uvicorn
    home = tempfile.mkdtemp(prefix="inox_qc3_t6_browser_")
    old_home, old_demo = os.environ.get("INOX_HYDRA_HOME"), os.environ.get("INOX_DEMO_DATA")
    os.environ["INOX_HYDRA_HOME"] = home
    os.environ.pop("INOX_DEMO_DATA", None)

    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()

    from app import app
    for name, module in list(sys.modules.items()):
        if name.rsplit(".", 1)[-1] == "browser_launcher" and module is not None:
            module.subprocess = types.SimpleNamespace(
                Popen=lambda argv, *a, **k: types.SimpleNamespace(pid=0, returncode=None, poll=lambda: None))
            module._try_open_in_running_browser = lambda *a, **k: None

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port,
                                           log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            _real_create(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        pytest.fail(f"the studio at {base} did not start")

    yield {"url": base, "posts": len(data["own"])}

    server.should_exit = True
    thread.join(timeout=5.0)
    if old_home is None:
        os.environ.pop("INOX_HYDRA_HOME", None)
    else:
        os.environ["INOX_HYDRA_HOME"] = old_home
    if old_demo is not None:
        os.environ["INOX_DEMO_DATA"] = old_demo
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as play:
        instance = play.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def screen(browser, studio):
    """
    A page at 1440x900, the size every section's bar is measured at, with
    service workers blocked.
    """
    context = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    page = context.new_page()
    page.goto(studio["url"], wait_until="networkidle")
    yield page
    context.close()


def _open(page, section):
    page.click(f'button[aria-label="{section}"]')
    page.wait_for_timeout(600)


def _count_text(page):
    """The "1-20 of 60" line the Posts screen prints beside its pager."""
    for text in page.locator("p").all_inner_texts():
        if re.fullmatch(r"\d+–\d+ of [\d,]+", text.strip()):
            return text.strip()
    return None


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

def test_the_posts_table_says_how_many_of_how_many_and_reaches_the_rest(screen, studio):
    _open(screen, "Posts")
    assert screen.locator("table").count() == 1, "Posts is a table"
    first = _count_text(screen)
    assert first is not None, "the screen prints how many posts it shows of how many there are"
    assert first.endswith(f"of {studio['posts']}")
    assert first.startswith("1–")
    rows_before = screen.locator("tbody tr").all_inner_texts()

    nxt = screen.locator('button[aria-label="Next page"]')
    assert nxt.is_enabled(), "there is more than one page, so Next is live"
    nxt.click()
    screen.wait_for_timeout(600)
    second = _count_text(screen)
    assert second != first and second.endswith(f"of {studio['posts']}")
    assert screen.locator("tbody tr").all_inner_texts() != rows_before
    assert screen.locator('button[aria-label="Previous page"]').is_enabled()

    # Back to where it started.
    screen.locator('button[aria-label="Previous page"]').click()
    screen.wait_for_timeout(600)
    assert _count_text(screen) == first


def test_the_pager_works_from_the_keyboard(screen):
    _open(screen, "Posts")
    first = _count_text(screen)
    nxt = screen.locator('button[aria-label="Next page"]')
    nxt.focus()
    assert screen.evaluate("document.activeElement?.getAttribute('aria-label')") == "Next page"
    screen.keyboard.press("Enter")
    screen.wait_for_timeout(600)
    assert _count_text(screen) != first


def test_a_row_opens_one_post_into_its_detail(screen):
    _open(screen, "Posts")
    excerpt = screen.locator("tbody tr").first.locator("button").first
    shown = excerpt.inner_text().strip()
    excerpt.click()
    screen.wait_for_timeout(700)
    dialog = screen.locator('div[role="dialog"][aria-label="Post detail"]')
    assert dialog.is_visible(), "the row opens the post rather than expanding in place"
    body = dialog.inner_text()
    # The whole post, not the row's 140 character excerpt.
    assert shown.split("\n")[0][:40].strip() in body.replace("\n", " ") or len(body) > len(shown)
    assert "WHO ENGAGED" in body.upper()
    screen.keyboard.press("Escape")
    screen.wait_for_timeout(400)
    assert dialog.count() == 0 or not dialog.is_visible()


def test_the_search_and_the_settle_filter_move_the_count(screen, studio):
    _open(screen, "Posts")
    everything = _count_text(screen)
    screen.fill('input[aria-label="Search your posts"]', "sourdough")
    screen.wait_for_timeout(900)
    narrowed = _count_text(screen)
    assert narrowed is not None and narrowed != everything
    assert not narrowed.endswith(f"of {studio['posts']}"), "a search narrows the count, not just the rows"

    screen.fill('input[aria-label="Search your posts"]', "")
    screen.wait_for_timeout(900)
    screen.click('button:has-text("Still growing")')
    screen.wait_for_timeout(900)
    growing = _count_text(screen)
    assert growing is None or not growing.endswith(f"of {studio['posts']}")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_analytics_prints_no_percentage_over_a_hundred(screen):
    _open(screen, "Analytics")
    screen.wait_for_timeout(900)
    text = screen.locator("body").inner_text()
    rates = [float(found) for found in re.findall(r"(\d+(?:\.\d+)?)% ENGAGEMENT", text.upper())]
    assert all(rate <= 100 for rate in rates), f"a rate over 100 is on screen: {rates}"
    # The rate the engine refuses is named, not printed, and a figure never
    # read says so rather than reading 0.
    assert "116.25" not in text


def test_the_comparison_table_is_paged_and_says_so(screen):
    _open(screen, "Analytics")
    screen.wait_for_timeout(900)
    body = screen.locator("body").inner_text()
    assert re.search(r"\d+–\d+ of [\d,]+, best first", body), "the table says how much of the history it shows"
    rows_before = screen.locator("tbody tr").all_inner_texts()
    nxt = screen.locator('button[aria-label="Next posts"]')
    assert nxt.is_enabled()
    nxt.click()
    screen.wait_for_timeout(700)
    assert screen.locator("tbody tr").all_inner_texts() != rows_before


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

def test_patterns_has_more_than_the_two_controls_it_had(screen):
    _open(screen, "Patterns")
    screen.wait_for_timeout(900)
    controls = screen.locator(
        "main button:visible, main input:visible, main select:visible, main a[href]:visible").count()
    assert controls > 2, f"Patterns still has {controls} controls"


def test_patterns_says_no_difference_rather_than_ranking_noise(screen):
    _open(screen, "Patterns")
    screen.wait_for_timeout(900)
    text = screen.locator("main").inner_text()
    # Either a form differed, or the screen says plainly that none did. What
    # it must not do is rank a difference its own posts cannot separate.
    lower = text.lower()
    assert ("no difference" in lower or "not enough posts" in lower or "went with more or fewer" in lower)
    # "went with", never "caused": this compares posts, it runs no experiment.
    assert "not causes" in lower
    assert not re.search(r"(caused by|causes more|increases your|will increase)", lower)
