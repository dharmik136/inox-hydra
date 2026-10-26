"""
"From your record" is a section of the rail, after Today.
=========================================================

Cycle 4, track 7, decisions 1 and 2 of the personalised daily ideas report:
the section is called "From your record", and it sits in the Now group,
third, after Today and Replies. Track 4 restructures the rail into five
groups in parallel and carries a guard over the ordered list; until that
merge the rail is flat and Replies does not exist, so this holds the entry
itself, its place straight after Today, and the three places that must know
a section exists: the router, the screen audit and the backend registry a
screen files annotations against.

A section named in the rail but routed nowhere is a dead click, which is the
defect tests/test_qc3_t7_sections_removed.py guards from the other side.
"""

import io
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

ENTRY = {
    "id": "record",
    "screenKey": "record",
    "label": "From your record",
    "blurb": "What from your own record, and what you asked, is worth writing from today",
}


def _read(*parts):
    with io.open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _rail_entries():
    """The rail's entries in order, as (id, the whole object literal)."""
    navigation = _read("studio", "ui", "src", "lib", "navigation.ts")
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", navigation, flags=re.S)
    block = code.split("STUDIO_SECTIONS", 1)[1]
    return re.findall(r'\{\s*id: "([a-z]+)"([^}]*)\}', block)


def test_the_entry_exists_with_its_id_label_blurb_and_screen_key():
    entries = dict(_rail_entries())
    assert ENTRY["id"] in entries, "the rail has no From your record entry"
    body = entries[ENTRY["id"]]
    for key in ("screenKey", "label", "blurb"):
        assert f'{key}: "{ENTRY[key]}"' in body, f"the entry's {key} is not {ENTRY[key]!r}: {body.strip()}"


def test_the_entry_follows_today():
    """Third in the Now group, after Today and Replies (the rail of track 4, merged)."""
    entries = _rail_entries()
    order = [entry_id for entry_id, _body in entries]
    assert "today" in order and "replies" in order and "record" in order
    assert order.index("replies") == order.index("today") + 1, order
    assert order.index("record") == order.index("replies") + 1, order
    assert 'group: "now"' in dict(entries)["record"], "the entry is not in the Now group"


def test_the_section_id_is_part_of_the_type():
    navigation = _read("studio", "ui", "src", "lib", "navigation.ts")
    union = navigation.split("export type SectionId", 1)[1].split(";", 1)[0]
    assert '"record"' in union, "SectionId does not admit the record section"


def test_the_router_opens_the_section():
    app = _read("studio", "ui", "src", "App.tsx")
    code = re.sub(r"\{/\*.*?\*/\}|//[^\n]*", "", app, flags=re.S)
    assert 'active === "record"' in code, "App.tsx routes nothing for the record section"
    assert "<RecordSurface" in code, "the record section renders no surface"
    assert os.path.exists(os.path.join(UI_SRC, "components", "RecordSurface.tsx"))


def test_the_screen_audit_walks_the_section():
    audit = _read("tools", "ui_audit.py")
    section_block = audit.split("SECTIONS = {", 1)[1].split("}", 1)[0]
    assert f'"record": "{ENTRY["label"]}"' in section_block, "tools/ui_audit.py does not walk the section"


def test_the_backend_registry_knows_the_screen_key():
    import devtools

    known = {screen["key"] for screen in devtools.SCREEN_REGISTRY.values()}
    assert ENTRY["screenKey"] in known, "annotations filed from the section would resolve to unknown"


def test_the_guard_is_not_vacuous():
    """A rail without the entry fails the first check, by construction of the parser."""
    navigation = _read("studio", "ui", "src", "lib", "navigation.ts")
    without = re.sub(r'\n\s*\{ id: "record"[^\n]*\n', "\n", navigation)
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", without, flags=re.S)
    block = code.split("STUDIO_SECTIONS", 1)[1]
    assert "record" not in dict(re.findall(r'\{\s*id: "([a-z]+)"([^}]*)\}', block))
