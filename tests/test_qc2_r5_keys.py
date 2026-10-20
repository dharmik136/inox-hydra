"""
Ctrl+S saves and Ctrl+B formats, in the Composer.
================================================

Cycle 2, batch R5, D-19. Neither key was handled, so in a browser Ctrl+S
opened Save Page As over the draft, and formatting was reachable only from the
selection toolbar.
"""

from qc2_r5_live import open_section, server, studio  # noqa: F401

WATCH = """
window.__keys = [];
window.addEventListener('keydown', (event) => {
  window.__keys.push([event.key, event.defaultPrevented]);
});
"""


def test_ctrl_s_saves_the_draft_instead_of_the_page(studio):
    page = studio["page"]
    page.add_init_script(WATCH)
    open_section(studio, "composer")
    body = page.get_by_label("Post body")
    body.fill("A post saved from the keyboard.")
    body.press("Control+s")
    # Not text=SAVED: UNSAVED contains it, so the wait passed at once and the
    # draft was read before the write landed. This is the state the bar shows
    # only once the save returned (ContextBar.tsx: "SAVED <time>").
    page.wait_for_function(
        """() => {
            const bar = document.body.innerText;
            return /(^|[^N])SAVED \\d/.test(bar);
        }""",
        timeout=15000,
    )
    assert ["s", True] in page.evaluate("window.__keys"), page.evaluate("window.__keys")
    drafts = studio["client"].get("/api/posts", params={"status": "draft"}).json()["posts"]
    assert any(post["content"] == "A post saved from the keyboard." for post in drafts), drafts


def test_ctrl_b_bolds_the_selection(studio):
    page = studio["page"]
    open_section(studio, "composer")
    body = page.get_by_label("Post body")
    body.fill("Bold this please")
    body.evaluate("(area) => area.setSelectionRange(0, 4)")
    body.press("Control+b")
    page.wait_for_function("() => !document.querySelector('[aria-label=\"Post body\"]').value.startsWith('Bold')")
    value = body.input_value()
    assert value.endswith(" this please") and not value.startswith("Bold"), value
