"""
Quality cycle 2026-10, batch F8: the Leads dossier's copy refusal points the
right way, and goes once a later copy works.

When the browser refused the copy, the dossier said "Select the text below",
but the drafted message sits above that line. And the refusal stayed on
screen after the next copy succeeded, so the dossier said COPIED and "the
browser refused the copy" at once.

Runs the built interface with the harness of tests/test_qc_f7_ui.py.
"""

from test_qc_f7_ui import _deny_clipboard, browser, studio, studio_url  # noqa: F401


def _allow_clipboard(page):
    page.evaluate(
        "() => Object.defineProperty(navigator, 'clipboard', {value: {writeText: () => Promise.resolve()},"
        " configurable: true})"
    )


def test_a_refused_copy_points_up_and_clears_after_a_copy_that_works(studio):
    session = studio()
    _deny_clipboard(session.page)
    page = session.open("Leads")
    main = page.locator("main")
    main.get_by_role("button", name="Peer question").first.click()
    copy = main.get_by_role("button", name="COPY", exact=True).first
    copy.wait_for(state="visible")

    copy.click()
    refusal = main.get_by_text("The browser refused the copy")
    refusal.wait_for(state="visible")
    text = refusal.inner_text()
    assert "above" in text and "below" not in text, f"the refusal points at the wrong place: {text!r}"

    _allow_clipboard(page)
    copy.click()
    main.get_by_role("button", name="COPIED", exact=True).first.wait_for(state="visible")
    assert main.get_by_text("The browser refused the copy").count() == 0, (
        "the refusal stays on screen after a copy that worked"
    )


def test_a_browser_without_a_clipboard_is_told_the_same(studio):
    session = studio()
    session.page.add_init_script("Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true});")
    page = session.open("Leads")
    main = page.locator("main")
    main.get_by_role("button", name="Peer question").first.click()
    main.get_by_role("button", name="COPY", exact=True).first.click()
    main.get_by_text("The browser refused the copy").wait_for(state="visible")
    assert not session.errors, session.errors

