"""
UI Visual Contract
==================
Python tests can pass while the interface is visibly broken. These check the
properties of the frontend that no functional test can see.

Each rule here exists because it was already violated:

- 16 var() references pointed at tokens that were never declared, so borders
  vanished, panels fell back to transparent and corners rendered square.
- 14 icon-only buttons had no accessible name, so a screen reader announced
  them as "button" with no indication of what they did.
- 125 decorative glyphs were exposed to assistive technology as unnamed images.
- There was no :focus-visible rule anywhere, so a keyboard user could not see
  where they were.
- Animation ran unconditionally, ignoring the operating system's reduced motion
  setting.

The last two tests are ratchets on existing debt. They do not demand the debt be
paid, only that it stops growing. When you reduce a count, lower the ceiling.
"""

import os
import re
from html.parser import HTMLParser

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend")
INDEX_HTML = os.path.join(FRONTEND, "index.html")
APP_JS = os.path.join(FRONTEND, "app.js")
STYLES_CSS = os.path.join(FRONTEND, "styles.css")

# Frozen ceilings. Lower them as the debt is paid; never raise them.
MAX_HEX_LITERALS_IN_JS = 42
MAX_INLINE_STYLES_IN_HTML = 284
MAX_INLINE_STYLES_IN_JS = 81

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr", "path", "use", "circle", "rect", "line",
    "polygon", "polyline", "stop", "ellipse",
}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def frontend():
    return {"css": _read(STYLES_CSS), "js": _read(APP_JS), "html": _read(INDEX_HTML)}


def test_every_design_token_referenced_is_declared(frontend):
    """A var() pointing at an undeclared token with no fallback resolves to nothing."""
    css = frontend["css"]
    declared = set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", css, re.M))
    blob = css + frontend["js"] + frontend["html"]

    broken = []
    for token, fallback in re.findall(r"var\(\s*(--[a-z0-9-]+)\s*(,)?", blob):
        if token not in declared and not fallback:
            broken.append(token)

    assert not broken, (
        f"These tokens are used without a fallback but never declared, so the "
        f"property silently resolves to nothing: {sorted(set(broken))}"
    )


def test_no_token_is_referenced_that_does_not_exist(frontend):
    """Even with a fallback, an undeclared token means the token system is fiction there."""
    css = frontend["css"]
    declared = set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", css, re.M))
    referenced = set(re.findall(r"var\(\s*(--[a-z0-9-]+)", css + frontend["js"] + frontend["html"]))
    undeclared = sorted(referenced - declared)
    assert not undeclared, (
        f"Referenced but never declared: {undeclared}. Declare them, or point the "
        f"component at a canonical token."
    )


def test_icon_only_buttons_have_an_accessible_name(frontend):
    """A button whose only content is a glyph announces as 'button' unless it is labelled."""
    unlabelled = []
    for match in re.finditer(r"<button\b([^>]*)>(.*?)</button>", frontend["html"], re.S):
        attrs, body = match.groups()
        has_glyph = "<svg" in body
        has_text = bool(re.sub(r"<[^>]+>", "", body).strip())
        if has_glyph and not has_text:
            if not re.search(r"aria-label=|aria-labelledby=|title=", attrs):
                line = frontend["html"][: match.start()].count("\n") + 1
                ident = re.search(r'id="([^"]+)"', attrs)
                unlabelled.append(f"index.html:{line} {ident.group(1) if ident else '(no id)'}")
    assert not unlabelled, f"Icon-only buttons with no accessible name: {unlabelled}"


def test_decorative_glyphs_are_hidden_from_assistive_technology(frontend):
    """Every app-symbol sits beside its own label, so it must not be announced separately."""
    exposed = re.findall(r'<svg(?![^>]*aria-hidden)[^>]*class="app-symbol', frontend["html"])
    assert not exposed, (
        f"{len(exposed)} decorative glyphs are exposed to assistive technology. "
        f'Add aria-hidden="true".'
    )


def test_keyboard_focus_is_visible(frontend):
    """Without a focus-visible rule a keyboard user cannot tell where they are."""
    assert ":focus-visible" in frontend["css"], "No :focus-visible rule in styles.css"


def test_reduced_motion_preference_is_honoured(frontend):
    """The operating system setting exists to stop animation. Honour it."""
    assert "prefers-reduced-motion" in frontend["css"], (
        "styles.css never checks prefers-reduced-motion"
    )


def test_stylesheet_braces_balance(frontend):
    """An unbalanced brace silently discards every rule after it."""
    css = re.sub(r"/\*.*?\*/", "", frontend["css"], flags=re.S)
    assert css.count("{") == css.count("}"), (
        f"Unbalanced braces in styles.css: {css.count('{')} open, {css.count('}')} close"
    )


def test_markup_is_structurally_sound(frontend):
    """A stray closing tag silently reparents everything after it."""

    class Checker(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.errors = []

        def handle_starttag(self, tag, attrs):
            if tag not in VOID_ELEMENTS:
                self.stack.append((tag, self.getpos()[0]))

        def handle_endtag(self, tag):
            if tag in VOID_ELEMENTS:
                return
            if self.stack and self.stack[-1][0] == tag:
                self.stack.pop()
            elif any(t == tag for t, _ in self.stack):
                index = max(i for i, (t, _) in enumerate(self.stack) if t == tag)
                unclosed = [f"<{t}> (line {ln})" for t, ln in self.stack[index + 1:]]
                self.errors.append(
                    f"line {self.getpos()[0]}: </{tag}> leaves unclosed: {', '.join(unclosed)}"
                )
                del self.stack[index:]
            else:
                self.errors.append(f"line {self.getpos()[0]}: stray </{tag}>")

    checker = Checker()
    checker.feed(frontend["html"])
    assert not checker.errors, f"Structural errors in index.html: {checker.errors[:5]}"
    assert not checker.stack, f"Tags never closed: {checker.stack[:5]}"


def test_hardcoded_colours_in_javascript_do_not_grow(frontend):
    """
    Ratchet. Colour belongs in the stylesheet, where the theme can reach it. A hex
    literal in a script is a colour that cannot follow the theme.
    """
    count = len(re.findall(r"#[0-9a-fA-F]{3,8}\b", frontend["js"]))
    assert count <= MAX_HEX_LITERALS_IN_JS, (
        f"app.js now holds {count} hardcoded colours, up from the frozen ceiling of "
        f"{MAX_HEX_LITERALS_IN_JS}. Use a var(--token) instead."
    )


def test_inline_styles_do_not_grow(frontend):
    """
    Ratchet. Inline style attributes bypass the design system and cannot be themed
    or overridden. The existing ones are debt; new ones should not appear.
    """
    in_html = len(re.findall(r'style="', frontend["html"]))
    in_js = len(re.findall(r'style="', frontend["js"]))
    assert in_html <= MAX_INLINE_STYLES_IN_HTML, (
        f"index.html now has {in_html} inline styles, up from {MAX_INLINE_STYLES_IN_HTML}. "
        f"Add a class to styles.css instead."
    )
    assert in_js <= MAX_INLINE_STYLES_IN_JS, (
        f"app.js now injects {in_js} inline styles, up from {MAX_INLINE_STYLES_IN_JS}. "
        f"Add a class to styles.css instead."
    )
