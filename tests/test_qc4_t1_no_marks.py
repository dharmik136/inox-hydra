"""
The bridge leaves no mark of its own in LinkedIn's page.
========================================================

Review finding S7 of cycle 4, track 1, and the owner's decision under D3.
Phase 1 added two marks to LinkedIn's document that any script there could
read: the card stamper wrote its run onto the root element as
data-inox-card-urns, for every user and with network reading off, and the
interceptor marked the root element data-inox-voyager. The decision kept
only data-urn on a feed card and the import banner with its Stop button.

So the stamper's run and the interceptor's answer travel as window messages,
on the channel the interceptor's captures already use, and the interceptor
is asked only while network reading is on. Every notice the bridge drew into
the page goes to the side panel, by way of the worker, which shows "!" on
the badge until the panel opens; a warning while a history import runs is a
sentence in the import's own banner, not a new element; the composer's
answer is the side panel's, which asked.

The guard reads every script that runs in LinkedIn's page, with comments,
strings and regular expressions blanked, and fails on any attribute set on
the root element or the body, and on any element inserted or attribute set
outside the three places the decision allows.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")


# ---------------------------------------------------------------------------
# Reading a script as code
# ---------------------------------------------------------------------------

REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^")
REGEX_KEYWORDS = ("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield",
                  "await")


def code_only(source):
    """The source with comments, string and template text and regex bodies blanked, offsets kept."""
    out = list(source)
    i, n = 0, len(source)
    templates = []  # open braces inside each ${ } of a template literal
    last_sig, last_word = "", ""

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = source[i]
        if source.startswith("//", i):
            j = source.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if source.startswith("/*", i):
            j = source.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and source[j] != c and source[j] != "\n":
                j += 2 if source[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
            last_sig, last_word = c, ""
            continue
        if c == "`" or (c == "}" and templates and templates[-1] == 0):
            if c == "}":
                templates.pop()
            j = i + 1
            while j < n and source[j] != "`" and not source.startswith("${", j):
                j += 2 if source[j] == "\\" else 1
            blank(i + 1, j)
            if source.startswith("${", j):
                templates.append(0)
                i = j + 2
                last_sig, last_word = "{", ""
            else:
                i = j + 1
                last_sig, last_word = "`", ""
            continue
        if c == "{" and templates:
            templates[-1] += 1
        elif c == "}" and templates:
            templates[-1] -= 1
        if c == "/" and (last_sig in ("",) or last_sig in REGEX_BEFORE or last_word in REGEX_KEYWORDS):
            j, in_class = i + 1, False
            while j < n and source[j] != "\n" and (source[j] != "/" or in_class):
                if source[j] == "\\":
                    j += 2
                    continue
                in_class = True if source[j] == "[" else (False if source[j] == "]" else in_class)
                j += 1
            blank(i + 1, j)
            i = j + 1
            last_sig, last_word = "/", ""
            continue
        if c.isalnum() or c in "_$":
            j = i
            while j < n and (source[j].isalnum() or source[j] in "_$"):
                j += 1
            last_sig, last_word = "a", source[i:j]
            i = j
            continue
        if not c.isspace():
            last_sig, last_word = c, ""
        i += 1
    return "".join(out)


def _named_functions(code):
    """(name, body start, body end) of each named function."""
    spans = []
    for match in re.finditer(r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(", code):
        depth, k = 0, match.end() - 1
        while k < len(code):
            depth += {"(": 1, ")": -1}.get(code[k], 0)
            if depth == 0:
                break
            k += 1
        start = code.index("{", k)
        depth, k = 0, start
        while k < len(code):
            depth += {"{": 1, "}": -1}.get(code[k], 0)
            if depth == 0:
                break
            k += 1
        spans.append((match.group(1), start, k))
    return spans


def _enclosing(spans, position):
    inside = [span for span in spans if span[1] <= position <= span[2]]
    return min(inside, key=lambda span: span[2] - span[1])[0] if inside else None


# Every way a script can put an element into the page, and every way it can
# set an attribute (the style attribute included). A copy made with cloneNode
# is not in the page: own_insights.js reads a repost card's own figures from a
# detached copy, and a copy could reach the page only through one of the
# calls below.
INSERTS = (
    r"\bcreateElement(?:NS)?\s*\(", r"\.appendChild\s*\(", r"\.insertBefore\s*\(",
    r"\.insertAdjacent(?:Element|HTML|Text)\s*\(", r"\.replaceChild\s*\(", r"\.replaceChildren\s*\(",
    r"\.replaceWith\s*\(", r"\.(?:append|prepend|after|before)\s*\(", r"\.(?:innerHTML|outerHTML)\s*\+?=(?!=)",
    r"\bdocument\s*\.\s*write(?:ln)?\s*\(", r"\.attachShadow\s*\(",
)
ATTRIBUTES = (
    r"\.setAttribute(?:NS)?\s*\(", r"\.toggleAttribute\s*\(", r"\.dataset\b",
    r"\.classList\s*\.\s*(?:add|toggle|replace)\s*\(", r"\.className\s*\+?=(?!=)",
    r"\.(?:id|title|lang|dir|hidden|slot)\s*=(?!=)", r"\.style\b",
)
ROOT_OR_BODY = re.compile(r"(?:\bdocumentElement|\bdocument\s*\.\s*body|\bbody)\s*$")


def _allowed(name, function, kind, at):
    """The three places decision D3 keeps, and nothing else. `at` is the source from the call on."""
    if name == "own_pages.js" and function == "banner":
        return True  # the import banner, its sentence and its Stop button
    if name == "card_urns.js" and function == "stampCardUrns" and kind == "attribute":
        return re.match(r"""\.setAttribute\(\s*['"]data-urn['"]""", at) is not None
    if name == "content.js" and function == "injectIntoLinkedInComposer" and kind == "insert":
        return re.match(r"""\.innerHTML\s*=\s*(""|'')\s*;""", at) is not None  # empties the composer it fills
    return False


def page_marks(name, source):
    """Every mark a script would leave in LinkedIn's page outside what is allowed, as (line, text)."""
    code = code_only(source)
    spans = _named_functions(code)
    lines = source.splitlines()
    found = []
    for kind, patterns in (("insert", INSERTS), ("attribute", ATTRIBUTES)):
        for pattern in patterns:
            for match in re.finditer(pattern, code):
                number = source.count("\n", 0, match.start()) + 1
                line = lines[number - 1]
                on_root = kind == "attribute" and ROOT_OR_BODY.search(code[:match.start()].rstrip()) is not None
                at = source[match.start():match.start() + 80]
                if on_root or not _allowed(name, _enclosing(spans, match.start()), kind, at):
                    found.append((number, line.strip()))
    return sorted(set(found))


def _page_scripts():
    """The scripts that run in LinkedIn's page: the manifest's, and the one the worker registers."""
    with open(os.path.join(EXT, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    names = [name for entry in manifest["content_scripts"] for name in entry["js"]]
    with open(os.path.join(EXT, "background.js"), encoding="utf-8") as handle:
        worker = handle.read()
    for registered in re.findall(r"\bjs:\s*\[([^\]]*)\]", worker):
        names += re.findall(r'"([\w.]+\.js)"', registered)
    return sorted(set(names))


def _source(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as handle:
        return handle.read()


def test_the_guard_reads_every_script_that_runs_in_linkedins_page():
    names = _page_scripts()
    for name in ("card_urns.js", "content.js", "own_pages.js", "voyager_interceptor.js"):
        assert name in names, f"{name} is not read"
    # It sees what it allows, so a blind reading cannot pass it.
    code = code_only(_source("own_pages.js"))
    banner = [span for span in _named_functions(code) if span[0] == "banner"]
    assert banner and "createElement" in code[banner[0][1]:banner[0][2]]


def test_no_script_marks_linkedins_page_beyond_the_post_id_and_the_import_banner():
    marks = {name: page_marks(name, _source(name)) for name in _page_scripts()}
    marks = {name: found for name, found in marks.items() if found}
    assert not marks, (
        "an extension script sets an attribute on LinkedIn's root element or body, or draws into the "
        f"page outside the import banner (decision D3): {marks}")


def test_the_reading_of_a_script_is_not_fooled_by_strings_comments_or_patterns():
    source = (
        "// document.body.appendChild(x)\n"
        "const a = 'document.documentElement.setAttribute(1)';\n"
        "const b = /createElement(/;\n"
        "const c = `${document.body.setAttribute('x', 1)}`;\n"
    )
    assert page_marks("content.js", source) == [(4, "const c = `${document.body.setAttribute('x', 1)}`;")]


# ---------------------------------------------------------------------------
# The same, in a browser: the run and the answer travel as messages
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pages():
    pytest.importorskip("playwright.sync_api")
    from qc_f3_pages import Pages
    p = Pages()
    yield p
    p.close()


ROOT_MARKS = """() => [document.documentElement, document.body]
  .flatMap((el) => Array.from(el.attributes).map((a) => a.name)).filter((n) => n.indexOf('inox') >= 0)"""
LISTEN = """() => { window.__posted = [];
  window.addEventListener('message', (e) => { if (e.data && e.data.source) window.__posted.push(e.data); }); }"""


def test_the_card_stamper_reports_by_message_and_leaves_no_mark(pages):
    from qc_f3_pages import page_html
    feed = page_html("<main><div class='feed-shared-update-v2'>One</div><div class='feed-shared-update-v2'>Two</div></main>")
    page = pages.open("/feed/", feed, scripts=("card_urns.js", "voyager_schema.js", "content.js"), before=LISTEN)
    page.clock.run_for(2000)
    page.wait_for_timeout(50)
    reports = [b for b in pages.sent(page, "/api/v1/bridge/capture") if b.get("extractor") == "card_urns"]
    assert reports and reports[0]["items_seen"] == 2, "the stamper's run never reached the capture log"
    assert page.evaluate(ROOT_MARKS) == [], "the stamper marked LinkedIn's document"
    sources = {m["source"] for m in page.evaluate("() => window.__posted")}
    assert sources == {"inox-card-urns"}, sources


def test_with_network_reading_off_the_bridge_asks_the_page_nothing(pages):
    from qc_f3_pages import page_html
    page = pages.open("/feed/", page_html("<main></main>"),
                      scripts=("voyager_interceptor.js", "voyager_schema.js", "content.js", "own_pages.js"),
                      storage={"networkReading": False}, before=LISTEN)
    page.clock.run_for(3000)
    page.wait_for_timeout(50)
    assert page.evaluate("() => window.__posted") == [], "the bridge posted into a page whose switch is off"
    assert page.evaluate(ROOT_MARKS) == []


def test_with_network_reading_on_the_interceptor_answers_and_marks_nothing(pages):
    from qc_f3_pages import page_html
    page = pages.open("/feed/", page_html("<main></main>"),
                      scripts=("voyager_interceptor.js", "voyager_schema.js", "content.js", "own_pages.js"),
                      storage={"networkReading": True})
    page.clock.run_for(100)
    page.wait_for_timeout(50)
    beats = pages.sent(page, "/api/v1/bridge/heartbeat")
    assert beats and beats[-1]["network_reading"]["injected"] is True
    assert page.evaluate(ROOT_MARKS) == [], "the interceptor marked LinkedIn's document"


# ---------------------------------------------------------------------------
# Notices: the side panel, or a sentence in the import's banner
# ---------------------------------------------------------------------------

ELEMENTS = "() => Array.from(document.body.querySelectorAll('*')).filter((e) => !e.closest('#studio-import-banner')).length"


def test_a_notice_goes_to_the_side_panel_and_nothing_is_drawn(pages):
    from qc_f3_pages import notice_text
    from test_qc_f3_engagers import FEED, MODAL, OPEN_MODAL
    page = pages.open("/feed/", FEED)
    page.evaluate("() => { window.__answers['/api/v1/crm/interactions/ingest'] = 'unreachable'; }")
    page.clock.run_for(5000)
    page.evaluate("() => document.getElementById('mine-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    drawn = page.evaluate(ELEMENTS)
    page.clock.run_for(6000)
    assert "could not reach your studio" in (notice_text(page) or ""), "the notice never reached the side panel"
    assert page.evaluate(ELEMENTS) == drawn, "a notice was drawn into LinkedIn's page"
    notice = [m for m in pages.sent(page) if m.get("action") == "PAGE_NOTICE"][-1]
    assert notice["kind"] == "warning"


def test_a_warning_while_an_import_runs_is_a_sentence_in_its_banner(pages):
    from qc_f3_pages import page_html
    posts = page_html("""
<main>
 <div id="expanded-2-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:activity:7386000000000000006">
   <div><a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a></div>
   <div data-testid="expandable-text-box">My own post about shipping a local-first app, written by me.</div>
   <button aria-label="9 reactions">9</button>
 </div>
</main>""", title="Test Creator | Activity | LinkedIn", lang="en")
    kept = """() => {
      window.__answers['/api/v1/self/imports/pending'] = { status: 'success', request: { id: 7, kind: 'posts' } };
      const base = window.__answer;
      window.__answer = (m) => (m.path === '/api/v1/self/posts/ingest'
        ? { status: 'error', kept: true, waiting: 3, error: 'kept' } : base(m));
    }"""
    page = pages.open("/in/test-creator/recent-activity/all/", posts,
                      scripts=("voyager_schema.js", "content.js", "own_pages.js"), before=kept)
    drawn = page.evaluate(ELEMENTS)
    page.clock.run_for(7000)
    banner = page.evaluate("() => { const b = document.getElementById('studio-import-banner'); return b ? b.innerText : null; }")
    assert banner and "importing your posts" in banner
    assert "kept and will be sent again" in banner, "the warning during the import is not in its banner"
    assert page.evaluate(ELEMENTS) == drawn, "something besides the import banner was drawn into the page"
