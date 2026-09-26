"""
React UI Contract
=================
The rules the React interface in studio/ui is held to.

This replaced tests/test_ui_visual_contract.py, which held the same rules over
the vanilla page. That page is gone: the React interface reaches every endpoint
family it did, so there is one interface and one contract.

Every rule below was carried across because the defect it guards is a property
of any themed interface, not of the page that happened to be there first:

- 16 var() references pointed at tokens that were never declared, so borders
  vanished, panels fell back to transparent and corners rendered square.
- 14 icon-only buttons had no accessible name, so a screen reader announced
  them as "button" with no indication of what they did.
- There was no :focus-visible rule anywhere, so a keyboard user could not see
  where they were.
- Animation ran unconditionally, ignoring the operating system's reduced motion
  setting.
- An unbalanced brace silently discards every rule after it.

Two ratchets came across as well, and both are far below where they started.
The vanilla page carried 42 hex literals in its JavaScript and 365 inline
styles; this interface carries 0 and 6. That is not an invitation to spend the
difference.

Structural checks read studio/frontend_next, which is build output. They skip
when it is absent, which is a legitimate state for a checkout without node.
The authoring checks read studio/ui/src and always run, so a checkout with no
build is still held to the rules that do not need one.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import glob
import io
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
TOKENS_CSS = os.path.join(UI_SRC, "styles", "tokens.css")
INDEX_CSS = os.path.join(UI_SRC, "styles", "index.css")
BUILT = os.path.join(REPO_ROOT, "studio", "frontend_next")

# Frozen ceilings. Lower them as the debt is paid; never raise them.
#
# Every inline style in this interface is computed geometry: where a measured
# fold rule sits, where a toolbar follows a selection, how tall a revealed
# paragraph is, how far along a progress bar the server says a task is. None
# of those is expressible as a class, which is the one case the vanilla rule
# was never arguing with. A colour or a spacing value appearing here is the
# regression this counts.
#
# Raised from 5 to 6 for the image studio's progress bar, which is a width
# the server reports. The ratchet did its job: it made that a decision with a
# reason rather than a line nobody looked at.
MAX_HEX_LITERALS_IN_SOURCE = 0
MAX_INLINE_STYLES = 6

# Never typed literally, or this file would break the rule it enforces, which
# is what tests/test_phase4_algorithmic_safety.py caught the moment it was.
EM_DASH = chr(8212)


def _source_files(pattern="*.tsx"):
    return sorted(glob.glob(os.path.join(UI_SRC, "**", pattern), recursive=True))


def _read(path):
    return io.open(path, encoding="utf-8").read()


def _built_file(*parts):
    path = os.path.join(BUILT, *parts)
    return path if os.path.exists(path) else None


def _built_asset(suffix):
    static = os.path.join(BUILT, "static")
    if not os.path.isdir(static):
        return None
    hits = sorted(p for p in glob.glob(os.path.join(static, f"*{suffix}")))
    return hits[0] if hits else None


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

def _declared_tokens(block):
    return set(re.findall(r"^\s*(--studio-[a-z0-9-]+)\s*:", block, re.M))


@pytest.fixture(scope="module")
def token_blocks():
    """The light block and the dark block, split on the dark selector."""
    source = _read(TOKENS_CSS)
    parts = re.split(r'\[data-theme="dark"\],\s*\n?:root:not\(\[data-theme="light"\]\)\s*\{', source)
    assert len(parts) == 2, (
        "tokens.css no longer has exactly one dark palette block. The whole theme "
        "mechanism is that both blocks declare the same names with different values."
    )
    return _declared_tokens(parts[0]), _declared_tokens(parts[1])


def test_every_token_referenced_is_declared():
    """
    A var() pointing at an undeclared token resolves to nothing, and the
    property it was setting silently does not apply.
    """
    declared = _declared_tokens(_read(TOKENS_CSS))
    referenced = set()
    for path in _source_files("*.tsx") + _source_files("*.ts") + _source_files("*.css"):
        referenced |= set(re.findall(r"var\((--studio-[a-z0-9-]+)", _read(path)))

    missing = sorted(referenced - declared)
    assert not missing, f"these tokens are used but never declared: {missing}"


def test_no_token_exists_only_in_the_dark_palette(token_blocks):
    """
    The dark block overrides; the light block is the base.

    A token declared only in the dark block is undefined under
    data-theme="light", so the light theme loses whatever it was setting. The
    reverse is fine and intended: fonts, radii, easing and motion durations are
    theme neutral and are declared once.
    """
    light, dark = token_blocks
    dark_only = sorted(dark - light)
    assert not dark_only, (
        f"declared in the dark palette but not the light one, so they vanish in light mode: {dark_only}"
    )


def test_every_colour_token_is_declared_in_both_palettes(token_blocks):
    """
    A colour declared once takes the same value in both themes.

    This is the failure the conventions document was written about: a colour
    added to the base block alone gives the dark theme a light value.
    """
    light, dark = token_blocks
    source = _read(TOKENS_CSS)
    light_block = re.split(r'\[data-theme="dark"\]', source)[0]

    colour_like = set()
    for name in light:
        match = re.search(rf"^\s*{re.escape(name)}\s*:\s*([^;]+);", light_block, re.M)
        if match and re.search(r"#[0-9a-fA-F]{3,8}|rgba?\(|color-mix\(", match.group(1)):
            colour_like.add(name)

    # Text placed on a signal fill is deliberately the same near black in both
    # themes, because both signal steps are light. It is a colour that is
    # correct to declare once.
    exempt = {"--studio-on-signal"}
    missing = sorted(colour_like - dark - exempt)
    assert not missing, (
        f"these are colours declared only in the light palette, so dark inherits a light value: {missing}"
    )


# ---------------------------------------------------------------------------
# Accessibility floor
# ---------------------------------------------------------------------------

def _opening_tag_end(source, start):
    """
    Index of the > that closes an opening JSX tag.

    Not source.find(">"), which is what this file used to do, and the reason the
    button guard below spent its life vacuous: onClick={() => handler()} puts a
    > inside the attribute list, so the "body" began mid attribute and the
    leftover className string counted as the button's visible text. Every button
    in this interface is written with an arrow handler, so the guard passed all
    of them without ever reading their contents.

    Braces and strings are tracked, so a > inside either is not the end of a tag.
    """
    depth = 0
    quote = None
    i = start
    while i < len(source):
        char = source[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ">" and depth == 0:
            return i
        i += 1
    return -1


def _button_parts(source):
    """Each button as (opening tag, body), with the tag boundary read properly."""
    for match in re.finditer(r"<button\b", source):
        end = _opening_tag_end(source, match.start())
        close = source.find("</button>", match.start())
        if end == -1 or close == -1 or close < end:
            continue
        yield source[match.start():end + 1], source[end + 1:close]


def _strip_elements(body):
    """
    Removes nested tags, leaving only what sits between them.

    Tags are skipped with the same brace aware scanner, not with <[^>]*>, for two
    reasons: a nested element's prop may contain a > inside an arrow function,
    and its props certainly contain braces. strokeWidth={1.75} is a brace in an
    attribute rather than a child expression, and counting it as content is how
    the first version of this check called an icon-only button "labelled".
    """
    out = []
    i = 0
    while i < len(body):
        if body[i] == "<":
            end = _opening_tag_end(body, i)
            if end == -1:
                break
            i = end + 1
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def _announces_something(body):
    """
    Whether a button body produces anything a screen reader can read.

    A child expression counts: <button>{section.label}</button> announces the
    label, and demanding a literal there would ask for an aria-label duplicating
    the text already on screen. A body of nothing but glyph elements does not
    count, because every decorative glyph in this interface is aria-hidden, which
    is exactly the case this guard exists for.
    """
    between = _strip_elements(body)
    return "{" in between or bool(between.strip())


def test_icon_only_buttons_have_an_accessible_name():
    """
    A button whose only content is a glyph announces as "button" unless it is
    labelled. Fourteen controls in the previous interface did exactly that.
    """
    offenders = []
    for path in _source_files("*.tsx"):
        source = _read(path)
        for head, body in _button_parts(source):
            has_name = "aria-label" in head or "aria-labelledby" in head
            if not has_name and not _announces_something(body):
                offenders.append(f"{os.path.relpath(path, REPO_ROOT)}: {' '.join(head.split())[:80]}")

    assert not offenders, "buttons with neither text nor an accessible name:\n" + "\n".join(offenders)


def test_the_accessible_name_guard_is_not_vacuous():
    """
    The guard above, held to its own claim.

    It passed an icon-only unnamed button for years because of the > in an arrow
    function, so the rule it enforces is planted here and the detection is
    asserted rather than assumed. A guard that cannot fail protects nothing, and
    this interface has already shipped fourteen buttons it did not catch.
    """
    unnamed = """
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="grid size-8 place-items-center"
      >
        <PanelRight className="size-4" strokeWidth={1.75} aria-hidden="true" />
      </button>
    """
    parts = list(_button_parts(unnamed))
    assert len(parts) == 1, f"the button was not found at all: {parts}"
    head, body = parts[0]
    assert "onClick" in head, "the opening tag stopped before the attributes ended"
    assert "PanelRight" in body, "the body was cut short of the button's contents"
    assert not _announces_something(body), (
        "a button holding one aria-hidden glyph is reported as announcing something, "
        "which is the exact defect this guard exists to catch"
    )

    named = unnamed.replace('type="button"', 'type="button" aria-label="Open inspector"')
    named_head, _ = list(_button_parts(named))[0]
    assert "aria-label" in named_head, "a label in the opening tag is no longer seen"

    labelled_by_text = """
      <button type="button" onClick={() => select(id)}>
        {section.label}
      </button>
    """
    _, text_body = list(_button_parts(labelled_by_text))[0]
    assert _announces_something(text_body), (
        "a button whose child expression renders its label was reported as unnamed"
    )


def test_decorative_glyphs_are_hidden_from_assistive_technology():
    """
    Every icon sits beside its own label or inside a labelled control, so the
    glyph itself must not be announced. 125 were announced as unnamed images.
    """
    offenders = []
    # lucide components are PascalCase single elements rendered with a size class.
    for path in _source_files("*.tsx"):
        source = _read(path)
        for match in re.finditer(r"<([A-Z][A-Za-z0-9]*)\s+([^>]*?)/>", source, re.S):
            attrs = match.group(2)
            if "className" in attrs and re.search(r"size-\[?\d", attrs):
                if "aria-hidden" not in attrs and "aria-label" not in attrs:
                    offenders.append(f"{os.path.relpath(path, REPO_ROOT)}: <{match.group(1)}>")

    assert not offenders, "icons exposed to assistive technology:\n" + "\n".join(sorted(set(offenders)))


def test_keyboard_focus_is_visible():
    """Without a focus-visible rule a keyboard user cannot tell where they are."""
    css = _read(INDEX_CSS)
    assert ":focus-visible" in css, "no :focus-visible rule exists in the stylesheet"
    assert re.search(r":focus-visible\s*\{[^}]*outline\s*:", css), (
        ":focus-visible exists but sets no outline"
    )


def test_reduced_motion_preference_is_honoured():
    """
    Motion is a first class token layer here, which makes this load bearing
    rather than polite.
    """
    css = _read(INDEX_CSS)
    assert "prefers-reduced-motion" in css, "the reduced motion preference is never consulted"


# ---------------------------------------------------------------------------
# Ratchets
# ---------------------------------------------------------------------------

def test_hardcoded_colours_in_source_do_not_grow():
    """
    Ratchet. A colour written into a component cannot follow the theme.

    tokens.css is the one file allowed to hold literals; it is where the
    palette is defined.
    """
    found = []
    for path in _source_files("*.tsx") + _source_files("*.ts"):
        for hit in re.findall(r"#[0-9a-fA-F]{3,8}\b", _read(path)):
            found.append(f"{os.path.relpath(path, REPO_ROOT)}: {hit}")

    assert len(found) <= MAX_HEX_LITERALS_IN_SOURCE, (
        f"{len(found)} hex literals in components, up from {MAX_HEX_LITERALS_IN_SOURCE}. "
        f"Use a token instead:\n" + "\n".join(found[:10])
    )


def test_inline_styles_do_not_grow():
    """
    Ratchet. An inline style cannot be overridden by a class or a media query.

    The five that exist are computed geometry and cannot be classes. A sixth
    should be one of those, not a colour or a spacing value.
    """
    count = sum(len(re.findall(r"style=\{", _read(path))) for path in _source_files("*.tsx"))
    assert count <= MAX_INLINE_STYLES, (
        f"{count} inline styles, up from {MAX_INLINE_STYLES}. "
        "Only measured geometry belongs here."
    )


def test_the_interface_holds_the_zero_em_dash_invariant():
    """The product wide rule, applied to the interface that ships."""
    offenders = []
    for path in _source_files("*.tsx") + _source_files("*.ts") + _source_files("*.css"):
        if EM_DASH in _read(path):
            offenders.append(os.path.relpath(path, REPO_ROOT))
    assert not offenders, f"em-dashes present in: {offenders}"


# ---------------------------------------------------------------------------
# Structural integrity of the built output
# ---------------------------------------------------------------------------

def test_the_built_stylesheet_braces_balance():
    """An unbalanced brace silently discards every rule after the error."""
    css_path = _built_asset(".css")
    if not css_path:
        pytest.skip("studio/frontend_next is not built in this checkout")
    css = _read(css_path)
    assert css.count("{") == css.count("}"), (
        f"unbalanced braces in the built stylesheet: {css.count('{')} open, {css.count('}')} close"
    )


def test_the_built_markup_is_structurally_sound():
    """A stray closing tag silently reparents everything after it."""
    html_path = _built_file("index.html")
    if not html_path:
        pytest.skip("studio/frontend_next is not built in this checkout")
    html = _read(html_path)
    for tag in ("html", "head", "body"):
        assert html.count(f"<{tag}") == html.count(f"</{tag}>"), f"<{tag}> is unbalanced"
    assert '<div id="root">' in html, "the React mount point is missing from the built page"


def test_the_built_page_loads_no_external_resource():
    """
    The product claims zero cloud egress, and a page that fetches a font or a
    script from a CDN breaks that claim on every launch. The previous interface
    opened three connections to Google on load.
    """
    html_path = _built_file("index.html")
    if not html_path:
        pytest.skip("studio/frontend_next is not built in this checkout")
    html = _read(html_path)
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert not external, f"the built page fetches from outside this machine: {external}"

    css_path = _built_asset(".css")
    if css_path:
        remote = re.findall(r"url\((https?://[^)]+)\)", _read(css_path))
        assert not remote, f"the built stylesheet fetches from outside this machine: {remote}"
