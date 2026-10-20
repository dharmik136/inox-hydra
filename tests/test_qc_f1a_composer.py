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


def test_reload_with_unsaved_text_asks_before_it_is_lost(new_page, studio_url, api):
    """
    Writing, then reloading or closing the tab, threw the text away without a
    word. The page now asks first, and only while there is something to lose.
    """
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    editor.click()
    page.keyboard.type("A paragraph nobody has saved yet.")
    expect(_status(page)).to_contain_text("UNSAVED")

    dialogs = []

    def answer(dialog):
        dialogs.append(dialog.type)
        dialog.accept()

    page.on("dialog", answer)
    page.reload(wait_until="networkidle")
    assert dialogs == ["beforeunload"], f"reloading over unsaved text asked {dialogs}"

    # Saved work is not nagged about.
    editor = _open_composer(page, studio_url)
    editor.click()
    page.keyboard.type("Saved this time.")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(_status(page)).to_contain_text("SAVED")
    page.reload(wait_until="networkidle")
    assert dialogs == ["beforeunload"], "a reload with nothing unsaved still asked"


def test_each_screen_has_an_address_that_survives_a_reload(new_page, studio_url):
    page = new_page()
    page.goto(studio_url + "/", wait_until="networkidle")
    page.get_by_role("button", name="Leads", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"#/leads$"))

    page.reload(wait_until="networkidle")
    expect(page.get_by_role("button", name="Leads", exact=True).first).to_have_attribute("aria-current", "page")


def test_back_moves_between_screens_instead_of_leaving_the_studio(new_page, studio_url):
    page = new_page()
    page.goto(studio_url + "/", wait_until="networkidle")
    page.get_by_role("button", name="Leads", exact=True).first.click()
    page.get_by_role("button", name="Docs", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"#/docs$"))

    page.go_back()
    expect(page).to_have_url(re.compile(r"#/leads$"))
    expect(page.get_by_role("button", name="Leads", exact=True).first).to_have_attribute("aria-current", "page")

    page.go_forward()
    expect(page.get_by_role("button", name="Docs", exact=True).first).to_have_attribute("aria-current", "page")


def test_a_link_to_a_screen_opens_that_screen(new_page, studio_url):
    """A help article or a teammate can point at a screen, and Setup does not pull it back."""
    page = new_page()
    page.goto(studio_url + "/#/queue", wait_until="networkidle")
    page.wait_for_timeout(300)
    expect(page.get_by_role("button", name="Queue", exact=True).first).to_have_attribute("aria-current", "page")


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


def _slow_formats(page):
    page.evaluate(
        """() => { const real = window.fetch;
                   window.fetch = (input, init) => String(input).includes('/api/format/')
                     ? new Promise(r => setTimeout(r, 1200)).then(() => real(input, init)) : real(input, init); }"""
    )


def _select(page, editor, start, length):
    editor.click()
    page.keyboard.press("Control+Home")
    for _ in range(start):
        page.keyboard.press("ArrowRight")
    for _ in range(length):
        page.keyboard.press("Shift+ArrowRight")


def test_typing_before_the_selection_still_formats_the_selected_words(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    _slow_formats(page)
    editor.fill("Say pricing is a design problem")
    _select(page, editor, 4, 7)
    page.get_by_role("button", name="Bold", exact=True).click()
    page.keyboard.press("Control+Home")
    page.keyboard.type("Honestly, ")
    page.wait_for_timeout(1800)
    value = editor.input_value()
    assert value.startswith("Honestly, Say \U0001d5fd\U0001d5ff"), f"the format was dropped or misplaced: {value!r}"
    assert value.endswith(" is a design problem")


def test_a_format_dropped_because_the_words_changed_says_so(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    _slow_formats(page)
    editor.fill("pricing is a design problem")
    _select(page, editor, 0, 7)
    page.get_by_role("button", name="Bold", exact=True).click()
    page.keyboard.press("Control+Home")
    page.keyboard.press("Delete")
    page.wait_for_timeout(1800)
    assert editor.input_value() == "ricing is a design problem", "the author's edit was undone"
    expect(page.get_by_role("status").filter(has_text="not applied")).to_be_visible()


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


def test_the_theme_follows_the_system_and_is_remembered(new_page, studio_url):
    page = new_page(color_scheme="light")
    page.goto(studio_url + "/", wait_until="networkidle")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")

    page.get_by_role("button", name="Switch to dark theme").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload(wait_until="networkidle")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")

    page.get_by_role("button", name="Switch to light theme").click()
    page.reload(wait_until="networkidle")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


def test_the_header_claims_no_live_connection_it_has_not_seen(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    page.goto(studio_url + "/#/setup", wait_until="networkidle")
    activity = page.locator("header").get_by_role("button", name=re.compile(r"^Activity"))
    expect(activity).to_be_visible()
    assert activity.locator(".animate-pulse").count() == 0, "a pulsing dot claims live activity"
    assert activity.locator(".bg-signal-green").count() == 0, "a green dot claims a bridge never seen"
    expect(activity).to_contain_text("not connected")

    editor = _open_composer(page, studio_url)
    editor.fill("A post")
    assert "DRAFT 01" not in page.locator("header").first.inner_text()


def test_phone_width_keeps_search_and_the_fold_label_on_screen(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page(viewport={"width": 375, "height": 812})
    page.goto(studio_url + "/#/setup", wait_until="networkidle")
    header_search = page.locator("header").get_by_role("button", name=re.compile("Search everything"))
    box = header_search.bounding_box()
    assert box and box["x"] + box["width"] <= 375, f"the header's Search runs off a 375 pixel screen: {box}"

    # A phone, and a 1024 pixel window with the inspector docked: both leave
    # the column a 40 pixel margin, which the full label does not fit.
    for width in (375, 1024):
        page.set_viewport_size({"width": width, "height": 812})
        editor = _open_composer(page, studio_url)
        editor.fill("This sentence is long enough to pass the LinkedIn fold on a phone. " * 4)
        page.wait_for_timeout(400)
        label = page.get_by_text("FOLD", exact=False).filter(has_text="140").first
        expect(label).to_be_visible()
        label_box = label.bounding_box()
        main_box = page.locator("main").bounding_box()
        assert label_box["x"] >= main_box["x"], f"at {width} the fold label sits under the rail: {label_box} vs {main_box}"


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082"
)


def test_media_delete_asks_and_reports_a_failure(new_page, studio_url, api):
    page = new_page()
    _open_composer(page, studio_url)
    page.get_by_role("button", name="Media", exact=True).click()
    page.get_by_label("Choose media to upload").set_input_files(
        files=[{"name": "square.png", "mimeType": "image/png", "buffer": PNG}]
    )
    delete = page.get_by_role("button", name="Delete square.png")
    expect(delete).to_be_attached()
    opacity = delete.evaluate("el => getComputedStyle(el).opacity")
    assert float(opacity) > 0, "the delete control is invisible until hovered"

    page.route("**/api/media/*", lambda route: route.fulfill(status=500, json={"detail": "The disk is read only."})
               if route.request.method == "DELETE" else route.continue_())
    dialogs = []

    def answer(dialog):
        dialogs.append(dialog.message)
        dialog.accept()

    page.on("dialog", answer)
    delete.click()
    assert dialogs and "square.png" in dialogs[0], "deleting a file did not ask first"
    expect(page.get_by_text("The disk is read only.")).to_be_visible()
    expect(page.get_by_role("button", name="Delete square.png")).to_be_visible()

    # Answering no leaves the file alone and sends nothing.
    page.unroute("**/api/media/*")
    page.remove_listener("dialog", answer)
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Delete square.png").click()
    page.wait_for_timeout(300)
    expect(page.get_by_role("button", name="Delete square.png")).to_be_visible()


def test_the_media_tab_and_preview_promise_nothing_the_composer_cannot_do(new_page, studio_url):
    page = new_page()
    _open_composer(page, studio_url)
    page.get_by_role("button", name="Media", exact=True).click()
    assert "CAROUSEL" not in page.get_by_label("Inspector", exact=True).inner_text().upper()
    page.get_by_role("button", name="Preview", exact=True).click()
    expect(page.get_by_role("tab", name="Mobile")).to_be_visible()
    assert page.get_by_role("tab", name="Carousel").count() == 0, "the Carousel tab offers slides nothing makes"


def _queue(api, content):
    from database import get_db

    post_id = api.post("/api/posts", json={"content": content, "status": "draft"}).json()["id"]
    conn = get_db()
    try:
        conn.execute(
            "UPDATE posts SET status = 'scheduled', scheduled_for = '2099-01-05T09:00:00+00:00' WHERE id = ?",
            (post_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return post_id


def _row(api, post_id):
    return next(row for row in api.get("/api/posts").json()["posts"] if row["id"] == post_id)


def test_a_typo_in_a_queued_post_is_fixed_from_the_queue(new_page, studio_url, api):
    """
    The server keeps a queued post's text from being overwritten by accident,
    so the interface needs a deliberate way in: Edit text on the Queue row,
    then Save, which asks first and saves that post's text on purpose.
    """
    _clear_posts(api)
    post_id = _queue(api, "A queued post with a tpyo.\n\nSecond paragraph.")
    page = new_page()
    page.goto(studio_url + "/#/queue", wait_until="networkidle")
    page.locator("li", has_text="A queued post with a tpyo.").get_by_role("button", name="Edit text").click()

    editor = page.get_by_label("Post body")
    expect(editor).to_have_value("A queued post with a tpyo.\n\nSecond paragraph.")
    expect(page).to_have_url(re.compile(r"#/composer$"))
    expect(page.get_by_text(re.compile("editing the text of a post that is already queued", re.I))).to_be_visible()

    asked = []
    page.on("dialog", lambda dialog: (asked.append(dialog.message), dialog.accept()))
    editor.fill("A queued post with a typo.\n\nSecond paragraph.")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(_status(page)).to_contain_text("SAVED")
    assert asked and "queued" in asked[0], asked
    row = _row(api, post_id)
    assert row["content"] == "A queued post with a typo.\n\nSecond paragraph."
    assert row["status"] == "scheduled", "correcting the text took the post out of the queue"


def test_saving_over_a_post_queued_meanwhile_offers_both_ways_out(new_page, studio_url, api):
    """
    A Composer still holding a post that was queued meanwhile is refused, and
    is offered Correct the queued post (asked first) or Save as a new draft,
    never Keep this version, which could not get past this refusal.
    """
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    editor.fill("First words of the post.")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(_status(page)).to_contain_text("SAVED")
    post_id = api.get("/api/posts").json()["posts"][0]["id"]
    from database import get_db

    conn = get_db()
    try:
        conn.execute("UPDATE posts SET status = 'scheduled' WHERE id = ?", (post_id,))
        conn.commit()
    finally:
        conn.close()

    editor.fill("First words of the post, corrected.")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(_status(page)).to_contain_text("SAVE FAILED")
    expect(page.locator("p", has_text="already queued")).to_be_visible()
    assert page.get_by_role("button", name="Keep this version").count() == 0
    expect(page.get_by_role("button", name="Save as a new draft")).to_be_visible()

    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Correct the queued post").click()
    page.wait_for_timeout(300)
    assert _row(api, post_id)["content"] == "First words of the post.", "answering Cancel still saved"

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Correct the queued post").click()
    expect(_status(page)).to_contain_text("SAVED")
    assert _row(api, post_id)["content"] == "First words of the post, corrected."
    assert _row(api, post_id)["status"] == "scheduled"


def test_save_as_a_new_draft_keeps_the_queued_post_and_the_new_text(new_page, studio_url, api):
    _clear_posts(api)
    post_id = _queue(api, "The queued text.")
    page = new_page()
    page.goto(studio_url + "/#/queue", wait_until="networkidle")
    page.locator("li", has_text="The queued text.").get_by_role("button", name="Edit text").click()
    editor = page.get_by_label("Post body")
    expect(editor).to_have_value("The queued text.")
    editor.fill("A different post, really.")
    page.get_by_role("button", name="Save as a new draft").click()
    expect(_status(page)).to_contain_text("SAVED")
    assert _row(api, post_id)["content"] == "The queued text."
    drafts = [row for row in api.get("/api/posts?status=draft").json()["posts"] if row["content"] == "A different post, really."]
    assert len(drafts) == 1

    # The Composer now holds the new draft: a further save goes there.
    editor.fill("A different post, really. Edited.")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(_status(page)).to_contain_text("SAVED")
    assert _row(api, drafts[0]["id"])["content"] == "A different post, really. Edited."
    assert _row(api, post_id)["content"] == "The queued text."
