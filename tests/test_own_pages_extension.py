"""
The extension script that reads the creator's own pages.
========================================================

own_pages.js runs on every LinkedIn page, so the rules that keep it to the
creator have to hold in its source, where a browser test cannot reach them from
this suite. These read that source.

The failure each one prevents:

  A path missing from the worker's allowlist. The relay refuses it, studio()
  resolves null, and the capture fails without a word. That is how the URN
  binding sat broken for weeks, and the audit found it the same way.

  A scroll without a request. The creator chose to let the studio scroll their
  activity pages, on the condition that it happens because they clicked
  something. A scroll reachable from anywhere else breaks that condition.

  A request to LinkedIn. The script reads the page the creator has open. It
  does not fetch.

  A stranger's profile sent to the studio. The studio would refuse it, but the
  data would still have left the page.
"""

import json
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")
OWN_PAGES = os.path.join(EXT, "own_pages.js")
BACKGROUND = os.path.join(EXT, "background.js")
MANIFEST = os.path.join(EXT, "manifest.json")
APP = os.path.join(REPO_ROOT, "studio", "backend", "app.py")


def _code(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//[^\n]*$", "", source)


def _function(source, name):
    match = re.search(r"(?:async\s+)?function\s+" + name + r"\s*\([^)]*\)\s*\{", source)
    assert match, f"{name} is missing from own_pages.js"
    depth, i = 0, match.end() - 1
    while i < len(source):
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            return source[match.start(): i + 1]
        i += 1
    raise AssertionError(f"could not find the end of {name}")


def test_the_manifest_loads_it():
    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    scripts = [js for entry in manifest["content_scripts"] for js in entry["js"]]
    assert "own_pages.js" in scripts


def test_every_studio_path_it_calls_is_relayed_and_exists():
    own = _code(OWN_PAGES)
    background = _code(BACKGROUND)
    with open(APP, encoding="utf-8") as handle:
        app = handle.read()

    called = set(re.findall(r'studio\(\s*"(/api/[^"]+)"', own))
    assert called, "own_pages.js no longer calls the studio at all"

    allow = set(re.findall(r'"(/api/[^"]+)"', background.split("RELAYABLE_PATHS")[1].split("]);")[0]))
    unrelayed = sorted(called - allow)
    assert not unrelayed, (
        f"own_pages.js calls {unrelayed}, which the worker refuses to relay, so "
        "those captures fail silently"
    )

    for path in called:
        assert re.search(r'@app\.post\("' + re.escape(path) + '"', app), (
            f"own_pages.js posts to {path}, which the studio does not serve as POST"
        )


def test_it_never_requests_anything_from_linkedin():
    own = _code(OWN_PAGES)
    assert not re.search(r"\bfetch\s*\(|XMLHttpRequest|\.open\(\s*['\"](GET|POST)", own), (
        "own_pages.js makes its own requests. It reads the page the creator has "
        "open; everything it sends goes to the studio through the worker"
    )


def test_it_scrolls_only_inside_a_requested_import():
    own = _code(OWN_PAGES)
    scrolls = [m.start() for m in re.finditer(r"scrollTo\s*\(|scrollBy\s*\(|scrollIntoView\s*\(", own)]
    assert scrolls, "the import no longer scrolls, so history beyond the first screen is never read"

    run_import = _function(own, "runImport")
    start = own.index(run_import)
    for position in scrolls:
        assert start <= position < start + len(run_import), (
            "own_pages.js scrolls outside runImport. Scrolling was agreed on the "
            "condition that it follows a click in the studio"
        )

    caller = _function(own, "onActivityPage")
    assert "imports/pending" in caller and "pending.request" in caller, (
        "runImport is no longer gated on a pending request from the studio"
    )
    assert own.count("runImport(") == 2, "runImport is called from somewhere other than the gated path"


def test_the_scroll_can_be_stopped_and_pauses_while_hidden():
    run_import = _function(_code(OWN_PAGES), "runImport")
    assert "stopRequested" in run_import, "the import cannot be stopped"
    assert "whileHidden" in run_import, "the import keeps scrolling a tab the creator is not looking at"
    assert "MAX_ROUNDS" in run_import, "the import has no upper bound"


def test_a_strangers_profile_does_not_leave_the_page():
    capture = _function(_code(OWN_PAGES), "captureProfile")
    guard = re.search(r"if\s*\(\s*mine\s*\?\s*mine\s*!==\s*vanity\s*:\s*evidence\.length\s*===\s*0\s*\)\s*return", capture)
    assert guard, (
        "captureProfile no longer returns early for a profile that is neither "
        "the confirmed creator's nor carries a sign of ownership"
    )
    assert guard.start() < capture.index("/api/v1/identity/observe"), (
        "the ownership check runs after the profile is sent"
    )


def test_activity_pages_are_read_only_when_they_are_yours():
    handler = _function(_code(OWN_PAGES), "onActivityPage")
    assert re.search(r"vanityOf\(window\.location\.href\)\s*!==\s*me\)\s*return", handler), (
        "someone else's activity page would be read as the creator's"
    )


def test_the_extension_pages_reach_the_studio_through_the_worker():
    """
    Audit W6. The popup and side panel fetched the studio directly, which
    carries no studio token, so every call was refused, and each page reported
    something else: "No prospects yet", "No scheduled posts", and a green
    "Online" written into the popup's HTML before anything was checked.
    """
    for name in ("popup.js", "sidepanel.js"):
        source = _code(os.path.join(EXT, name))
        assert not re.search(r"\bfetch\s*\(", source), (
            f"{name} calls the studio directly again, without the token, so every call is refused"
        )

    with open(os.path.join(EXT, "popup.html"), encoding="utf-8") as handle:
        popup_html = handle.read()
    assert not re.search(r'id="server-status"[^>]*>\s*Online', popup_html), (
        "the popup says Online before it has checked anything"
    )


def test_panel_reads_are_for_the_extensions_own_pages_only():
    background = _code(BACKGROUND)
    handler = background[background.index('message.action === "PANEL_API"'):]
    handler = handler[:handler.index("return true;\n  }\n\n  if (message.action")]
    assert "sender.tab" in handler, "a content script inside a LinkedIn page could read the studio through this"
    assert 'method: "GET"' in handler, "panel reads can do more than read"
    assert "PANEL_PATHS" in handler, "panel reads are not limited to a list of paths"


def test_the_readers_match_linkedins_rebuilt_pages():
    """
    Measured on a live profile and post, 27 Sep 2026: hashed class names, no
    h1, no section anchors, comments with no comment classes. These pin the
    handles that survived, so a change back to class names is deliberate.
    """
    own = _code(OWN_PAGES)
    content = _code(os.path.join(EXT, "content.js"))
    assert "isSelfProfile" in own, "LinkedIn's own self-profile marker is no longer read"
    assert "Primary content" in own, "the top card is no longer found by its label"
    assert "nameFromTitle" in own, "the name no longer falls back to the page title"
    assert "experienceStream" in own, "experience is no longer read as a stream of headers and roles"
    assert '"commentList"' in content, "the rebuilt layout's comment list is no longer read"
    assert "ReactionFacepile" in content, "reactor avatars can hide a commenter again"


def test_the_sidebar_cannot_veto_your_own_profile():
    """"People you may know" puts "Invite X to connect" on every profile, including yours."""
    evidence = _function(_code(OWN_PAGES), "selfEvidence")
    assert "topCard()" in evidence and "visitorInCard" in evidence


def test_post_text_keeps_its_line_breaks():
    """
    Found on the live import: the reader collapsed every newline, so 18 of 18
    posts were stored as one line and the opening line was lost.
    """
    reader = _function(_code(OWN_PAGES), "cardText")
    assert r'split("\n")' in reader and r'join("\n")' in reader, "post text is flattened to one line again"
