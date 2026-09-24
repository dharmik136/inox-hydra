"""
The Grounding Panel
===================
What a creator is shown before they let a source be read, and before its
material reaches a draft.

This suite was written against the vanilla page's Settings card. That page was
retired and the card moved to studio/ui, so every check here moved with it. The
guarantees are unchanged; what they read is not.

Two of them changed shape rather than subject. The vanilla card built markup by
hand, so escaping every value an MCP server supplies, and never interpolating
source text into a template literal, were the difference between showing a name
and running it. React escapes interpolated values, so the equivalent question
is whether anything opts out of that, which is what the first two tests now
ask.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import io
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PANEL = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "GroundingWorkspace.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")


@pytest.fixture(scope="module")
def panel():
    if not os.path.exists(PANEL):
        pytest.fail("the grounding panel is gone; the feature it fronts has not")
    return io.open(PANEL, encoding="utf-8").read()


@pytest.fixture(scope="module")
def api():
    return io.open(API, encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Values that arrive from a source
# ---------------------------------------------------------------------------

def test_no_source_value_is_written_as_raw_markup(panel):
    """
    The values that arrive from an MCP server, its name, its description and
    the material itself, are not the studio's text. The vanilla card escaped
    each one by hand. React escapes interpolated values, so what matters here
    is that nothing opts out.
    """
    assert "dangerouslySetInnerHTML" not in panel, (
        "the grounding panel writes raw markup, so a source controls what renders"
    )


def test_the_whole_interface_never_opts_out_of_escaping(panel):
    """
    Guards the reasoning above rather than this one file. If the interface
    starts writing raw markup anywhere, the argument that React escaping covers
    source values stops being true by construction.
    """
    import glob

    offenders = []
    for path in glob.glob(os.path.join(REPO_ROOT, "studio", "ui", "src", "**", "*.tsx"), recursive=True):
        if "dangerouslySetInnerHTML" in io.open(path, encoding="utf-8").read():
            offenders.append(os.path.relpath(path, REPO_ROOT))
    assert not offenders, f"raw markup is written in: {offenders}"


# ---------------------------------------------------------------------------
# What the creator is agreeing to
# ---------------------------------------------------------------------------

def test_the_command_is_shown_to_the_creator(panel):
    """
    They are agreeing to run it. An agreement to something invisible is not
    one, so the command is rendered beside the name rather than hidden behind
    it.
    """
    assert "server.command.join" in panel, (
        "the command a source runs is no longer shown, so the creator is agreeing "
        "to something they cannot see"
    )


def test_the_panel_says_that_adding_runs_a_command(panel):
    """The creator is told what they are agreeing to, where they agree to it."""
    assert "STORES A COMMAND THIS STUDIO WILL EXECUTE" in panel.upper(), (
        "the form no longer says that adding a source stores a command this "
        "machine will run"
    )


def test_adding_is_labelled_as_not_enabling(panel):
    """
    The two acts are separate in the API, and the button says so. Agreeing that
    a command exists and agreeing to be read by it are different.
    """
    assert "switched off" in panel, "the add control no longer says it does not enable"


def test_adding_sends_no_enabled_field(api):
    """
    The API has no enabled field on this request on purpose. An interface that
    invented one would collapse the two acts back together.
    """
    start = api.index("export async function addMcpServer(")
    body = api[start:api.index("export async function", start + 10)]
    assert "enabled" not in body, "the add call sends an enabled field, which the API does not take"


def test_the_command_is_sent_as_a_list(api, panel):
    """
    A command stays a list and never reaches a shell. The panel splits the
    typed text itself and shows the tokens back, so what is stored is not in
    question.
    """
    assert "commandTokens" in panel, "the command is no longer tokenised before it is sent"
    assert "RUNS AS" in panel.upper(), "the tokens are not shown back before they are stored"
    assert re.search(r"command:\s*string\[\]", api), "the command is no longer typed as a list"


# ---------------------------------------------------------------------------
# Egress
# ---------------------------------------------------------------------------

def test_the_panel_renders_the_egress_answer(panel):
    """
    The backend computes, on every gather, whether material is about to leave
    the machine. It used to tell nobody.
    """
    assert "egress.summary" in panel, "the egress answer is computed and still not shown"


def test_egress_is_rendered_on_load_and_on_preview(panel):
    """
    Once at the point of deciding, and again with the material in hand. A
    creator who opens the panel and one who previews are asking the same
    question at different moments.
    """
    assert panel.count("egress.summary") >= 2, (
        "the egress answer is shown in only one of the two places it is needed"
    )


def test_local_and_remote_are_not_styled_the_same(panel):
    """A single neutral style for both is the interface declining to say."""
    assert "leaves_this_machine" in panel, "the panel does not branch on where material goes"
    for tone in ("signal-orange", "signal-green"):
        assert tone in panel, f"the panel has no {tone} treatment to distinguish the two cases"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def test_a_toggle_follows_the_state_the_server_achieved(panel):
    """
    Not the state the click asked for. A toggle left on after a failed write
    tells a creator a source is being read when it is not, which is the wrong
    direction for this particular lie.
    """
    start = panel.index("setMcpServerEnabled(")
    following = panel[start:start + 200]
    assert "await load()" in following, (
        "the toggle does not re-read from the server after writing, so it shows "
        "the state that was requested rather than the state that was reached"
    )


def test_a_server_that_is_down_is_named_in_the_preview(panel):
    """Otherwise the creator wonders why their posts read generic again."""
    assert "preview.errors" in panel, "a source that failed is not named in the preview"


def test_the_preview_reads_the_same_path_a_draft_takes(api):
    """
    A preview of something adjacent to the real thing is a description of it.
    The route gathers from the enabled servers exactly as a draft does, so the
    interface calls that route rather than assembling its own answer.
    """
    assert '"/api/v1/mcp/preview"' in api, "the interface no longer calls the preview route"
