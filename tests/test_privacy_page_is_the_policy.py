"""
The published page says everything the policy says.
====================================================

`release/privacy.html` is the file served at the public address both browser
stores require. It is generated from `docs/PRIVACY_POLICY.md` by
`tools/build_privacy_page.py`.

The risk a generator introduces is a silent one: a renderer that does not
recognise a construct drops the line, the page still looks finished, and the
published policy is missing a clause that the repository's own tests say is
there. So this reads the rendered page back and asserts that every line of the
policy survived it, comparing on letters and digits alone so that punctuation,
wrapping and markup cannot hide a difference.

It also holds that the committed page is current, which is what stops the
source and the published text from drifting apart between releases.
"""

import html
import io
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POLICY = os.path.join(REPO, "docs", "PRIVACY_POLICY.md")
PAGE = os.path.join(REPO, "release", "privacy.html")
TOOL = os.path.join(REPO, "tools", "build_privacy_page.py")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _letters(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _page_text():
    body = _read(PAGE).split("<main>", 1)[1].split("</main>", 1)[0]
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


def test_the_page_exists_and_is_a_whole_document():
    page = _read(PAGE)
    assert page.startswith("<!doctype html>")
    assert "<title>Privacy policy: Inox Hydra Bridge</title>" in page
    # Self-contained: a policy page that fetches a stylesheet or a script from
    # somewhere else is a policy page that can stop looking like one, or stop
    # rendering, on a reviewer's machine. Checked by the tags that load things,
    # not by hostnames: the third-party table names several hostnames as text,
    # which is the policy doing its job.
    for loader in ("<script", "<link", "<iframe", " src=", "@import"):
        assert loader not in page, f"the page loads something with {loader!r}"


def test_every_line_of_the_policy_is_on_the_page():
    policy = _read(POLICY)
    page_letters = _letters(_page_text())
    missing = []
    for raw in policy.split("\n"):
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue
        # A table's divider row carries no text.
        if line.startswith("|") and re.fullmatch(r"\|[\s|:-]+\|", line):
            continue
        # List markers and heading hashes are markup, not words.
        line = re.sub(r"^(?:[-*]\s+|\d+\.\s+|#{1,4}\s+|>\s*(?:\[!NOTE\])?\s*)", "", line)
        chunk = _letters(line)
        if len(chunk) > 12 and chunk not in page_letters:
            missing.append(line[:80])
    assert not missing, (
        "the published page is missing text the policy has, so the renderer "
        "dropped something: " + "; ".join(missing)
    )


def test_no_markup_leaked_into_the_reader_s_text():
    text = _page_text()
    assert "**" not in text, "bold markers are being shown to the reader"
    assert not re.search(r"\|\s*-{3,}", text), "a table divider is being shown as text"
    assert "[!NOTE]" not in text


def test_the_tables_survived():
    """
    The third-party destinations are a table. Flattened into paragraphs they
    would still read, which is exactly why this is asserted rather than eyed.
    """
    page = _read(PAGE)
    assert page.count("<table>") >= 1
    text = _page_text()
    for destination in ("www.linkedin.com", "api.openai.com", "image.pollinations.ai",
                        "api.telegram.org"):
        assert destination in text, f"{destination} is no longer listed"


def test_the_committed_page_is_what_the_policy_renders_to():
    """
    The one that catches a policy edited without rebuilding the page.
    """
    done = subprocess.run([sys.executable, TOOL, "--check"],
                          capture_output=True, text=True, cwd=REPO)
    assert done.returncode == 0, done.stderr or done.stdout


def test_the_renderer_refuses_what_it_does_not_understand():
    """
    The property the whole arrangement rests on: an unknown construct raises
    instead of vanishing. Checked by handing the renderer one.
    """
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_privacy_page", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # A fenced block with tildes: no rule covers it, and a renderer that
    # shrugged would publish the policy with this clause gone.
    try:
        module.render("~~~\nthe clause nobody would notice was missing\n~~~\n")
    except ValueError as error:
        assert "not a construct" in str(error), error
    else:
        raise AssertionError("the renderer accepted a construct it has no rule for")
