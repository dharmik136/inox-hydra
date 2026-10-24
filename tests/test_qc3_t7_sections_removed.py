"""
The Swipe File and Command are gone, and nothing a creator can reach wanted them.
=================================================================================

Cycle 3, batch T7, decision D1 ("Command and Swipe File must earn their place
or fold into the screen they duplicate") and D3.

  Swipe File  `/api/inspirations` and `/api/v1/intelligence/templates` both
              served `intelligence_sync.get_templates` over one
              `viral_templates` table: the Composer drew the rows as the hook
              rail, the Swipe File drew the same twelve as a specimen wall
              (ONEVIEW "Swipe File is the Composer's hook rail, rendered
              twice"; MAKING section 1.10). Nothing could put a specimen in
              (no POST route exists) or take one out, and the screen's own
              banner said its figures were nobody's measurement. Folded into
              the rail, which already reads the same rows.
  Command     147 characters, three controls, 2.2% ink. The only thing it can
              act on is the Composer draft, which it took by a tick box, and
              its answer could not reach that draft. Folded into the
              Composer's Prompt panel, beside the draft and under the
              disclosure that says what goes with a request.

What this holds: the component files are deleted rather than unlinked, no
section id survives in the rail or the router, no surface still imports them,
and the two things that did point at the Swipe File (the command palette's
specimen results and the backend that tells them where to open) now point at
the Composer, so neither is a dead click. The endpoints are deliberately
untouched: `/api/inspirations` still serves Ctrl+K's hook form search and
`/api/ai/command` still answers the Prompt panel, so no route was removed and
tests/test_endpoint_reachability.py's counts are unchanged.
"""

import io
import json
import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

GONE = ("SwipeSurface.tsx", "CommandSurface.tsx")
GONE_IDS = ("swipe", "command")

# Everything a creator's copy of the product is built from. The extension, the
# command line and the help are included because a section can be named from
# any of them, and a name that opens nothing is the defect this guards.
SEARCHED = (
    os.path.join(REPO_ROOT, "studio", "ui", "src"),
    os.path.join(REPO_ROOT, "studio", "extension"),
    os.path.join(REPO_ROOT, "studio", "backend"),
    os.path.join(REPO_ROOT, "docs", "help"),
    os.path.join(REPO_ROOT, "studio_cli.py"),
    os.path.join(REPO_ROOT, "tools", "ui_audit.py"),
)
SUFFIXES = (".ts", ".tsx", ".js", ".py", ".md", ".html", ".json")


def _files():
    for root in SEARCHED:
        if os.path.isfile(root):
            yield root
            continue
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "dist")]
            for name in names:
                if name.endswith(SUFFIXES):
                    yield os.path.join(base, name)


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# Deleted, not unlinked
# ---------------------------------------------------------------------------

def test_the_two_components_are_deleted_from_the_tree():
    for name in GONE:
        path = os.path.join(UI_SRC, "components", name)
        assert not os.path.exists(path), f"{name} is still in the tree, only unlinked from the router"


def test_nothing_imports_or_renders_the_two_components():
    for path in _files():
        source = _read(path)
        for name in GONE:
            stem = name[: -len(".tsx")]
            assert f"from \"./{stem}\"" not in source and f'from "@/components/{stem}"' not in source, (
                f"{os.path.relpath(path, REPO_ROOT)} still imports {stem}"
            )
            assert f"<{stem} " not in source and f"<{stem}/>" not in source, (
                f"{os.path.relpath(path, REPO_ROOT)} still renders {stem}"
            )


# ---------------------------------------------------------------------------
# No section id, in the rail or anywhere a creator can type
# ---------------------------------------------------------------------------

def test_the_rail_no_longer_offers_the_two_sections():
    navigation = _read(os.path.join(UI_SRC, "lib", "navigation.ts"))
    # Comments may say why they went; the type and the rail may not list them.
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", navigation, flags=re.S)
    for section in GONE_IDS:
        assert f'"{section}"' not in code, f"the rail still declares the {section} section"
    assert "STUDIO_SECTIONS" in navigation


def test_the_router_has_no_branch_for_either_section():
    app = _read(os.path.join(UI_SRC, "App.tsx"))
    code = re.sub(r"\{/\*.*?\*/\}|//[^\n]*", "", app, flags=re.S)
    for section in GONE_IDS:
        assert f'active === "{section}"' not in code, f"App.tsx still routes {section}"


def test_the_screen_audit_walks_only_sections_that_exist():
    """tools/ui_audit.py names each rail label, and a stale one reads as a failure."""
    audit = _read(os.path.join(REPO_ROOT, "tools", "ui_audit.py"))
    section_block = audit.split("SECTIONS = {", 1)[1].split("}", 1)[0]
    for section in GONE_IDS:
        assert f'"{section}"' not in section_block, f"the audit still walks the {section} section"


# ---------------------------------------------------------------------------
# What pointed at the Swipe File points at the Composer, not at nothing
# ---------------------------------------------------------------------------

def test_a_hook_form_found_in_search_opens_a_screen_that_exists():
    """
    The palette's specimen results said "Shows in Swipe File" and navigated to
    a section that no longer exists, which would have been a dead click.
    """
    import app as app_module
    from fastapi.testclient import TestClient

    sections = set(re.findall(r'id: "([a-z]+)"', _read(os.path.join(UI_SRC, "lib", "navigation.ts"))))
    opens = set(re.findall(r'SearchOpens = ([^;]+);', _read(os.path.join(UI_SRC, "lib", "api.ts"))))
    assert opens, "the search result's destinations are no longer declared"
    for destination in re.findall(r'"([a-z]+)"', " ".join(opens)):
        assert destination in sections, f"search can open {destination!r}, which the rail does not have"

    client = TestClient(app_module.app)
    answer = client.get("/api/v1/search?q=the&limit=6")
    assert answer.status_code == 200, answer.text
    for specimen in answer.json().get("groups", {}).get("specimens", []):
        assert specimen["opens"] in sections, specimen
        assert specimen["opens"] != "swipe"


def test_the_palette_names_no_section_the_rail_does_not_have():
    palette = _read(os.path.join(UI_SRC, "components", "CommandPalette.tsx"))
    assert "Swipe File" not in palette, "the palette still offers the Swipe File"


# ---------------------------------------------------------------------------
# The capability is still reachable where it was folded in
# ---------------------------------------------------------------------------

def test_the_instruction_box_is_in_the_prompt_panel_with_the_draft():
    panel = _read(os.path.join(UI_SRC, "components", "PromptPanel.tsx"))
    assert "runAiCommand" in panel, "the Prompt panel cannot run an instruction"
    assert "draft" in panel, "the Prompt panel does not take the draft the instruction is about"
    # The answer can be used without selecting it with the mouse, which is the
    # one thing the section it came from could not do.
    assert "clipboard" in panel, "an answer still cannot be copied"
    inspector = _read(os.path.join(UI_SRC, "components", "Inspector.tsx"))
    assert "<PromptPanel draft={draft} />" in inspector, "the panel is not given the draft"


def test_the_endpoints_behind_both_sections_still_answer():
    """
    Neither route was removed: one still serves Ctrl+K's hook form search, the
    other the Prompt panel. A removal that took them would have broken both.
    """
    import app as app_module
    from fastapi.testclient import TestClient

    client = TestClient(app_module.app)
    assert client.get("/api/inspirations?limit=5").status_code == 200
    assert client.get("/api/ai/status").status_code == 200


def test_the_built_interface_carries_neither_section():
    built = os.path.join(REPO_ROOT, "studio", "frontend_next")
    if not os.path.isdir(built):
        pytest.skip("the interface is not built")
    for base, _dirs, names in os.walk(built):
        for name in names:
            if not name.endswith((".js", ".html")):
                continue
            source = _read(os.path.join(base, name))
            assert "Shows in Swipe File" not in source, f"{name} still ships the Swipe File"
            assert "Agent runs and local model routing" not in source, f"{name} still ships Command"
