"""
The grounding panel shows what a source handed over, and escapes it.
====================================================================

The MCP client was built, tested, wired into hook generation, and had no
interface. A server could only be added by calling Python, so the feature a
creator would actually want was unreachable to them.

Two properties of this panel matter more than the rest of it.

  Everything a source returns is escaped before it reaches the page. That text
  comes from a process on the creator's own machine, not from us, and a note
  containing a script tag is a note right up until it is injected into the
  document. This is the one place in the studio where arbitrary text from an
  arbitrary local program is rendered.

  The egress line is never omitted. The backend computes on every call whether
  gathered material is about to leave the machine, and until this panel
  existed it told nobody. A creator deciding whether to connect their notes
  needs that answer before they connect them.
"""

import os
import re
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS = os.path.join(REPO_ROOT, "studio", "frontend", "app.js")
INDEX = os.path.join(REPO_ROOT, "studio", "frontend", "index.html")
STYLES = os.path.join(REPO_ROOT, "studio", "frontend", "styles.css")

NODE = shutil.which("node")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def panel():
    """Just the grounding panel, so a match elsewhere in app.js cannot pass for one here."""
    source = _read(APP_JS)
    start = source.index("function initGroundingPanel")
    return source[start:]


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

def test_every_value_a_source_supplies_is_escaped(panel):
    """
    The values that arrive from an MCP server: the server name it was given,
    its command, and the title and body of whatever it returned. Each is
    rendered, so each has to be escaped.
    """
    for field in ("server.name", "item.title", "item.text", "item.server", "item.error"):
        pattern = r"escapeHtml\(\s*" + re.escape(field)
        assert re.search(pattern, panel), (
            f"{field} reaches the page without escapeHtml, so a note "
            f"containing markup is injected into the document"
        )


def test_no_template_literal_interpolates_source_text(panel):
    """
    A template literal is where an unescaped value hides most easily, because
    it reads like ordinary string building. The panel builds its markup by
    concatenation so every interpolation is visible at the call site.
    """
    interpolations = re.findall(r"\$\{([^}]*)\}", panel)
    for expression in interpolations:
        assert "escapeHtml" in expression, (
            f"a template literal interpolates {expression!r} without escaping"
        )


def test_the_command_is_shown_to_the_creator(panel):
    """
    They are agreeing to run it. An agreement to something invisible is not
    one, so the command is on screen next to the toggle that enables it.
    """
    assert "server.command" in panel
    assert "mcp-cmd" in panel


# ---------------------------------------------------------------------------
# Honesty
# ---------------------------------------------------------------------------

def test_the_panel_renders_the_egress_answer(panel):
    assert "renderEgress" in panel
    assert "leaves_this_machine" in panel, (
        "the panel does not read the egress flag, so it cannot warn that "
        "material is about to leave the machine"
    )


def test_egress_is_rendered_on_load_and_on_preview(panel):
    """
    Once, at the point of deciding, and again with the material in hand. A
    single call at load would go stale the moment the provider changed.
    """
    assert panel.count("renderEgress(") >= 3, (
        "egress is rendered fewer times than it is computed, so one of the "
        "two moments a creator needs it is unreported"
    )


def test_local_and_remote_are_not_styled_the_same():
    """
    A single neutral style for both is the interface declining to say.
    Staying on the machine is reassurance; leaving is a warning.
    """
    styles = _read(STYLES)
    assert ".mcp-egress.is-local" in styles
    assert ".mcp-egress.is-remote" in styles

    remote = styles[styles.index(".mcp-egress.is-remote"):]
    remote = remote[:remote.index("}")]
    assert "color:" in remote and "background:" in remote


def test_a_toggle_follows_the_state_the_server_achieved(panel):
    """
    Not the state the click asked for. A toggle left on after a failed write
    tells the creator their drafts are grounded when they are not, which is
    the same defect the queue pause was rewritten for.
    """
    assert "body.enabled !== wanted" in panel, (
        "the toggle does not verify the state it achieved"
    )
    assert "event.target.checked = !wanted" in panel


def test_a_server_that_is_down_is_named_in_the_preview(panel):
    """Otherwise the creator wonders why their posts read generic again."""
    assert "body.errors" in panel or "errors = body.errors" in panel
    assert "mcp-error" in panel


# ---------------------------------------------------------------------------
# It is actually reachable
# ---------------------------------------------------------------------------

def test_the_panel_markup_exists():
    markup = _read(INDEX)
    for element in (
        'id="mcp-server-list"',
        'id="mcp-egress"',
        'id="btn-mcp-add"',
        'id="btn-mcp-preview"',
        'id="mcp-preview"',
    ):
        assert element in markup, f"the panel is missing {element}"


def test_the_panel_says_that_adding_runs_a_command():
    """
    The creator is told what they are agreeing to, in the place they agree to
    it, rather than in a document they will not read.
    """
    markup = _read(INDEX)
    block = markup[markup.index('id="mcp-server-list"'):]
    block = block[:block.index("settings-card", 10)] if "settings-card" in block[10:] else block
    assert "command the studio will run" in block, (
        "nothing on screen says that adding a source runs a command"
    )


def test_adding_is_labelled_as_not_enabling():
    """The two acts are separate in the API, and the button should say so."""
    markup = _read(INDEX)
    assert "Add, switched off" in markup


@pytest.mark.skipif(NODE is None, reason="node is required to parse the frontend")
def test_the_frontend_still_parses():
    result = subprocess.run([NODE, "--check", APP_JS], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
