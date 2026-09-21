"""
Icon System Contract
====================
The studio draws every icon from one inline SVG sprite in index.html. Two rules
in that system had already been broken silently before anything checked them:
the interface referenced two symbols that were never defined, so those buttons
drew empty space, and nothing noticed because no test looked.

These tests pin the contract documented in docs/ICON_SYSTEM.md:

1. Every referenced symbol exists, and every defined symbol is accounted for.
2. Symbols carry no colour of their own, so they inherit currentColor.
3. Geometry is uniform: one 24x24 grid, one stroke weight.
4. Names follow sym-<role>-<name>, with role drawn from a closed set.
5. studio/frontend/icons.manifest.json matches the sprite exactly, so the
   record of where each glyph came from cannot drift from what ships.

When adding an icon, update the sprite and the manifest together. These tests
fail loudly if you update only one.
"""

import json
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend")
INDEX_HTML = os.path.join(FRONTEND, "index.html")
APP_JS = os.path.join(FRONTEND, "app.js")
STYLES_CSS = os.path.join(FRONTEND, "styles.css")
MANIFEST = os.path.join(FRONTEND, "icons.manifest.json")

VALID_ROLES = {"sec", "act", "mode", "brand"}
SYMBOL_NAME = re.compile(r"^sym-[a-z0-9]+(-[a-z0-9]+)*$")
UTILITY_SYMBOLS = {"sym-refresh", "sym-close"}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def sprite():
    html = _read(INDEX_HTML)
    js = _read(APP_JS)
    return {
        "html": html,
        "js": js,
        "defined": re.findall(r'<symbol id="(sym-[a-z0-9-]+)"', html),
        "referenced": set(re.findall(r'href="#(sym-[a-z0-9-]+)"', html + js)),
        "blocks": dict(
            (m.group(1), m.group(0))
            for m in re.finditer(r'<symbol id="(sym-[a-z0-9-]+)".*?</symbol>', html, re.S)
        ),
    }


@pytest.fixture(scope="module")
def manifest():
    return json.loads(_read(MANIFEST))


def test_every_referenced_symbol_is_defined(sprite):
    """The regression that shipped: two symbols were used but never defined, drawing nothing."""
    missing = sorted(sprite["referenced"] - set(sprite["defined"]))
    assert not missing, (
        f"These symbols are referenced but not defined in the sprite: {missing}. "
        f"Every reference to a missing symbol renders as empty space with no error."
    )


def test_no_duplicate_symbol_ids(sprite):
    """Duplicate ids mean the later definition silently wins."""
    seen, dupes = set(), []
    for s in sprite["defined"]:
        if s in seen:
            dupes.append(s)
        seen.add(s)
    assert not dupes, f"Duplicate symbol ids in the sprite: {sorted(set(dupes))}"


def test_symbol_names_follow_the_role_convention(sprite):
    """Names are sym-<role>-<name>, so a symbol's purpose is readable from its id."""
    offenders = []
    for s in sprite["defined"]:
        if s in UTILITY_SYMBOLS:
            continue
        if not SYMBOL_NAME.match(s):
            offenders.append((s, "not lowercase kebab-case"))
            continue
        role = s.split("-")[1]
        if role not in VALID_ROLES:
            offenders.append((s, f"unknown role '{role}', expected one of {sorted(VALID_ROLES)}"))
    assert not offenders, f"Symbol naming violations: {offenders}"


def test_symbols_inherit_currentcolor(sprite):
    """
    A symbol must not carry its own colour. The exporter emits stroke="white",
    which would make every icon invisible on the light theme.
    """
    offenders = []
    for sym, block in sprite["blocks"].items():
        head = block[: block.index(">") + 1]
        body = block[block.index(">") + 1:]
        if 'stroke="currentColor"' not in head:
            offenders.append((sym, "symbol does not set stroke=currentColor"))
        body_strokes = re.findall(r'stroke="([^"]+)"', body)
        hardcoded = [v for v in body_strokes if v != "currentColor"]
        if hardcoded:
            offenders.append((sym, f"hardcoded stroke colour in geometry: {hardcoded}"))
        if re.search(r'fill="(?!none)(?!currentColor)[^"]+"', body):
            offenders.append((sym, "hardcoded fill colour in geometry"))
    assert not offenders, f"Symbols that will not follow the theme: {offenders}"


def test_symbol_geometry_is_uniform(sprite):
    """One grid and one stroke weight, so icons sit together at every size."""
    offenders = []
    for sym, block in sprite["blocks"].items():
        head = block[: block.index(">") + 1]
        vb = re.search(r'viewBox="([^"]+)"', head)
        if not vb or vb.group(1) != "0 0 24 24":
            offenders.append((sym, f"viewBox {vb.group(1) if vb else 'missing'}, expected 0 0 24 24"))
        if not re.search(r'<(path|rect|circle|line|polyline|polygon)', block):
            offenders.append((sym, "symbol contains no geometry"))
    assert not offenders, f"Geometry violations: {offenders}"


def test_manifest_matches_the_sprite(manifest, sprite):
    """The provenance record must describe exactly what ships, no more and no less."""
    documented = set(manifest["symbols"])
    shipped = set(sprite["defined"])

    undocumented = sorted(shipped - documented)
    assert not undocumented, (
        f"These symbols ship but are absent from icons.manifest.json: {undocumented}. "
        f"Add them to the manifest so their source is recorded."
    )
    phantom = sorted(documented - shipped)
    assert not phantom, (
        f"The manifest documents symbols that are not in the sprite: {phantom}."
    )


def test_manifest_records_a_source_for_every_symbol(manifest):
    """Every glyph states where it came from, so the set can be regenerated or relicensed."""
    for sym, entry in manifest["symbols"].items():
        assert entry.get("source"), f"{sym} has no recorded source"
        assert entry.get("role"), f"{sym} has no recorded role"
        if entry["source"] != "hand-authored":
            assert entry.get("figma_node_id"), (
                f"{sym} claims an iconset source but records no Figma node id"
            )


def test_manifest_reference_counts_are_accurate(manifest, sprite):
    """A stale count hides an icon that quietly stopped being used."""
    actual = {}
    blob = sprite["html"] + sprite["js"]
    for sym in manifest["symbols"]:
        actual[sym] = len(re.findall(rf'href="#{re.escape(sym)}"', blob))
    wrong = {
        s: (manifest["symbols"][s]["references"], actual[s])
        for s in actual
        if manifest["symbols"][s]["references"] != actual[s]
    }
    assert not wrong, (
        f"icons.manifest.json reference counts are stale (manifest, actual): {wrong}. "
        f"Regenerate the manifest after changing icon usage."
    )


def test_size_classes_in_the_manifest_exist_in_the_stylesheet(manifest):
    """The documented size ramp has to be the one the stylesheet actually defines."""
    css = _read(STYLES_CSS)
    for klass, px in manifest["size_classes"].items():
        assert re.search(rf'\.{re.escape(klass)}\s*(,[^{{]*)?{{', css), (
            f"Size class .{klass} is documented in the manifest but absent from styles.css"
        )


def test_sprite_carries_no_em_dashes(sprite):
    """The project forbids the character across all source, including generated markup."""
    for sym, block in sprite["blocks"].items():
        assert chr(0x2014) not in block, f"Em-dash found in symbol {sym}"


def test_icon_system_is_documented():
    """The decisions live in the repository, not only in a conversation."""
    doc = os.path.join(REPO_ROOT, "docs", "ICON_SYSTEM.md")
    assert os.path.exists(doc), "docs/ICON_SYSTEM.md is missing"
    content = _read(doc)
    for required in ("sym-", "currentColor", "icons.manifest.json", "coolicons", "24"):
        assert required in content, f"docs/ICON_SYSTEM.md does not cover '{required}'"
