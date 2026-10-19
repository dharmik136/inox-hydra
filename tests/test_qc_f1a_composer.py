"""
Composer editing and drafts, driven in a real browser
=====================================================
The quality cycle's F1a batch: unsaved work, applying hooks, saving drafts,
formatting, the strip's counts, screen addresses, the theme and the marks in
the header. Each test drives the built interface (studio/frontend_next) in
headless Chromium against an in-process studio, the way
tests/test_e2e_browser_flows.py does, because every one of these defects lived
in the interaction between the editor and the page rather than in one function.

Every context blocks service workers. The studio registers one for
installability, and a request it serves never reaches page.route, so a test
that intercepts the network without this is not intercepting it.
"""

import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

BUILT_INDEX = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
if not os.path.exists(BUILT_INDEX):
    pytest.skip("studio/frontend_next is not built (npm --prefix studio/ui run build)", allow_module_level=True)

from app import app  # noqa: E402
from database import init_db  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def studio_url():
    """A studio with its own throwaway home, serving the built interface."""
    home = tempfile.mkdtemp(prefix="inox_qc_f1a_")
    previous = os.environ.get("INOX_HYDRA_HOME")
    os.environ["INOX_HYDRA_HOME"] = home
    os.environ["INOX_DEMO_DATA"] = "1"
    init_db()

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        raise RuntimeError("the studio did not start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=3.0)
    if previous is not None:
        os.environ["INOX_HYDRA_HOME"] = previous
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def api(studio_url):
    """The same studio, called directly, for arranging and checking rows."""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def new_page(browser):
    """Opens a page in a fresh context. Several per test model several tabs."""
    contexts = []

    def make(**options):
        options.setdefault("viewport", {"width": 1280, "height": 800})
        context = browser.new_context(service_workers="block", **options)
        contexts.append(context)
        return context.new_page()

    yield make
    for context in contexts:
        context.close()


def _clear_posts(api):
    for row in api.get("/api/posts").json()["posts"]:
        api.delete(f"/api/posts/{row['id']}")


def _open_composer(page, studio_url):
    page.goto(studio_url + "/", wait_until="networkidle")
    page.get_by_role("button", name="Composer", exact=True).first.click()
    editor = page.get_by_label("Post body")
    expect(editor).to_be_visible()
    return editor


def _status(page):
    return page.locator("header [role=status]").first


def _rows_with(api, content):
    return [row for row in api.get("/api/posts").json()["posts"] if row["content"] == content]


def test_a_hook_replaces_only_the_opening_when_the_blank_line_holds_a_space(new_page, studio_url, api):
    """
    Text pasted from LinkedIn keeps blank lines that are not empty: a space,
    or the U+2800 spacer people use so the gap survives. Applying a hook then
    replaced the whole post. It replaces the opening, and Undo puts it back.
    """
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    for spacer in (" ", "⠀"):
        draft = f"My own opening line.\n{spacer}\nThe body I wrote over an hour.\n{spacer}\nThe closing."
        editor.fill(draft)
        card = page.get_by_role("button", name=re.compile(r"^Apply ")).first
        card.click()
        value = editor.input_value()
        assert value.endswith(f"\n{spacer}\nThe body I wrote over an hour.\n{spacer}\nThe closing."), (
            f"the body did not survive a hook with {spacer!r} on the blank line: {value!r}"
        )
        assert not value.startswith("My own opening line."), "the hook was not applied"

        page.get_by_role("button", name=re.compile(r"^Undo ")).click()
        assert editor.input_value() == draft, "Undo did not restore the opening"


def test_windows_alt_codes_and_other_fields_never_apply_a_hook(new_page, studio_url, api):
    """
    Alt+0149 on a Windows numpad types a bullet. Each numpad digit arrives as
    keydown with altKey, which applied hooks 1, 4 and 9 in turn. The shortcut
    also fired while typing in the inspector's own fields.
    """
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    draft = "My opening paragraph, written carefully.\n\nThree lessons:\n"
    editor.fill(draft)
    for digit in "0149":
        editor.evaluate(
            """(el, d) => el.dispatchEvent(new KeyboardEvent('keydown', {key: d, code: 'Numpad' + d,
                 altKey: true, location: 3, bubbles: true, cancelable: true}))""",
            digit,
        )
    page.wait_for_timeout(300)
    assert editor.input_value() == draft, "a numpad Alt code applied a hook"

    # macOS Option+digit types a symbol (Option+8 is the bullet); that is the
    # author's character, not a shortcut.
    editor.evaluate(
        """el => el.dispatchEvent(new KeyboardEvent('keydown', {key: '•', code: 'Digit8',
             altKey: true, bubbles: true, cancelable: true}))"""
    )
    page.wait_for_timeout(200)
    assert editor.input_value() == draft, "Option+8 on a Mac applied a hook"

    page.get_by_role("button", name="Media", exact=True).click()
    concept = page.get_by_label("Image concept")
    concept.click()
    page.keyboard.press("Alt+Digit2")
    page.wait_for_timeout(300)
    assert editor.input_value() == draft, "Alt+2 typed in the image concept box changed the post"

    # The shortcut itself still works from the editor, and can be undone.
    editor.click()
    page.keyboard.press("Alt+Digit1")
    expect(editor).not_to_have_value(draft)
    page.get_by_role("button", name=re.compile(r"^Undo ")).click()
    expect(editor).to_have_value(draft)


def test_a_double_click_on_save_writes_one_draft(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    text = f"Double click test {time.time()}"
    editor.fill(text)
    # Three clicks inside one task, before React can re-render between them.
    page.evaluate(
        """() => { const save = [...document.querySelectorAll('header button')]
                     .find(b => b.textContent.trim() === 'Save');
                   save.click(); save.click(); save.click(); }"""
    )
    expect(_status(page)).to_contain_text("SAVED")
    page.wait_for_timeout(500)
    assert len(_rows_with(api, text)) == 1, "one Save gesture created several drafts"


def test_save_is_disabled_while_a_save_is_running(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    editor.fill("Slow save")
    page.evaluate(
        """() => { const real = window.fetch;
                   window.fetch = (input, init) => (init && init.method === 'POST' && String(input).endsWith('/api/posts'))
                     ? new Promise(r => setTimeout(r, 800)).then(() => real(input, init)) : real(input, init); }"""
    )
    save = page.get_by_role("button", name="Save", exact=True)
    save.click()
    expect(save).to_be_disabled()
    expect(_status(page)).to_contain_text("SAVED")
    expect(save).to_be_enabled()


def test_words_typed_while_a_save_runs_are_not_called_saved(new_page, studio_url, api):
    """A save that returns after the author typed more must not mark the newer text SAVED."""
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    editor.fill("First words")
    page.evaluate(
        """() => { const real = window.fetch;
                   window.fetch = (input, init) => (init && init.method === 'POST' && String(input).endsWith('/api/posts'))
                     ? new Promise(r => setTimeout(r, 800)).then(() => real(input, init)) : real(input, init); }"""
    )
    page.get_by_role("button", name="Save", exact=True).click()
    editor.click()
    page.keyboard.press("End")
    page.keyboard.type(" and more")
    page.wait_for_timeout(1500)
    expect(_status(page)).to_contain_text("UNSAVED")


def test_a_failed_save_shows_its_reason_on_screen(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    editor.fill("")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(_status(page)).to_contain_text("SAVE FAILED")
    # On screen, not in a hover tooltip, and in the status region a screen
    # reader announces.
    expect(page.get_by_text("There is nothing written to save.", exact=True)).to_be_visible()
    expect(_status(page)).to_contain_text("There is nothing written to save.")
    assert page.locator("header [title]").count() == 0, "the reason is still in a tooltip"

    editor.fill("x" * 6000)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_text("Post content exceeds maximum 5,000 character limit.", exact=True)).to_be_visible()

    # Editing again clears the old reason.
    editor.fill("short")
    expect(page.get_by_text("Post content exceeds maximum 5,000 character limit.", exact=True)).to_have_count(0)


def test_a_save_over_a_draft_changed_in_another_tab_is_refused(new_page, studio_url, api):
    """
    The same draft open in two tabs: whichever saved last overwrote the other,
    and the first still said SAVED. The later save is now refused with a
    reason, and the author can still choose to keep their version.
    """
    _clear_posts(api)
    original = "Shared opening.\n\nShared body."
    created = api.post("/api/posts", json={"content": original, "status": "draft"}).json()["id"]

    first = new_page()
    second = new_page()
    editor_a = _open_composer(first, studio_url)
    editor_b = _open_composer(second, studio_url)
    expect(editor_a).to_have_value(original)
    expect(editor_b).to_have_value(original)

    from_a = original + "\n\nTab A's closing paragraph."
    editor_a.fill(from_a)
    first.get_by_role("button", name="Save", exact=True).click()
    expect(_status(first)).to_contain_text("SAVED")

    from_b = "Tab B fixed a typo.\n\nShared body."
    editor_b.fill(from_b)
    second.get_by_role("button", name="Save", exact=True).click()
    expect(_status(second)).to_contain_text("SAVE FAILED")
    expect(second.locator("p", has_text="changed in another window")).to_be_visible()
    stored = [row for row in api.get("/api/posts").json()["posts"] if row["id"] == created][0]
    assert stored["content"] == from_a, "the stale tab overwrote the newer save"

    second.get_by_role("button", name=re.compile("keep this version", re.I)).click()
    expect(_status(second)).to_contain_text("SAVED")
    stored = [row for row in api.get("/api/posts").json()["posts"] if row["id"] == created][0]
    assert stored["content"] == from_b


def test_typing_while_a_format_request_runs_is_kept(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    page.evaluate(
        """() => { const real = window.fetch;
                   window.fetch = (input, init) => String(input).includes('/api/format/')
                     ? new Promise(r => setTimeout(r, 1200)).then(() => real(input, init)) : real(input, init); }"""
    )
    editor.fill("pricing is a design problem")
    editor.click()
    page.keyboard.press("Control+Home")
    for _ in range(7):
        page.keyboard.press("Shift+ArrowRight")
    page.get_by_role("button", name="Bold", exact=True).click()
    page.keyboard.press("End")
    page.keyboard.type(" and here is why")
    page.wait_for_timeout(1800)
    value = editor.input_value()
    assert value.endswith(" and here is why"), f"the words typed during the request are gone: {value!r}"
    assert value.startswith("\U0001d5fd\U0001d5ff"), f"the format was not applied: {value!r}"
    page.keyboard.type("!")
    assert editor.input_value().endswith("why!"), "the caret was pulled away from where the author was typing"


def test_a_format_left_alone_keeps_its_selection_for_the_next_one(new_page, studio_url, api):
    """Chaining formats still works when nothing was typed in between."""
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    editor.fill("pricing is a design problem")
    editor.click()
    page.keyboard.press("Control+Home")
    for _ in range(7):
        page.keyboard.press("Shift+ArrowRight")
    page.get_by_role("button", name="Bold", exact=True).click()
    expect(editor).to_have_value(re.compile("^\U0001d5fd"))
    page.wait_for_timeout(200)
    assert editor.evaluate("el => [el.selectionStart, el.selectionEnd]") == [0, 14]


def test_the_strip_shows_the_count_against_linkedins_limit(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    strip = page.locator('header p[aria-live="off"]')
    editor.fill("a" * 2999)
    expect(strip).to_contain_text("2,999 / 3,000")
    expect(strip.locator(".text-signal-orange-text", has_text="/ 3,000")).to_have_count(0)

    # Devanagari vowel signs are characters the limit counts, as the Audit does.
    hindi = "नमस्ते " * 450
    editor.fill(hindi)
    counted = api.post("/api/v1/gstack/audit", json={"content": hindi}).json()["audit"]["gates"]["gate_2_eng_manager"]["char_count"]
    expect(strip).to_contain_text(f"{counted:,} / 3,000")
    expect(strip).to_contain_text(f"{len(hindi):,} / 3,000")
    expect(strip.locator(".text-signal-orange-text", has_text="/ 3,000")).to_be_visible()
