"""
A machine without browsers collects the whole suite.
======================================================

Release 2.7.0 was tagged and did not publish. The desktop installers built on
all three platforms; the portable Windows job failed, and because the publish
job is every-asset-or-none, nothing shipped.

The cause was not the product. Five of cycle 3's browser tests imported
Playwright at the top of the module:

    from playwright.sync_api import expect

The quality workflow installs Playwright, so the whole suite ran there and the
fault was invisible for the length of the cycle. The release workflow's
portable Windows job does not install it, because that job builds a
distributable and needs no browser. On that machine the five modules raised
ModuleNotFoundError while pytest was still collecting, and a collection error
is not a skip: it stops the run. Forty other modules in this suite skipped
cleanly in the same job.

What this holds is the contract those forty keep: a module that needs a
browser says so to pytest before it imports one, so a machine without
Playwright reports a skip and carries on. It is a static read of the tree
rather than a run, so it costs nothing and it fails in the editor rather than
in a release.
"""

import io
import os
import re

TESTS = os.path.dirname(os.path.abspath(__file__))

# `from playwright...` / `import playwright...` at the start of a line: module
# level, which is what pytest executes while collecting. An import inside a
# function or a fixture runs only when that test runs, and a test that runs
# has already passed the module's own skip.
TOP_LEVEL_IMPORT = re.compile(r"^(?:from playwright|import playwright)", re.M)
GUARD = re.compile(r"importorskip\(\s*[\"']playwright")


def _modules():
    for name in sorted(os.listdir(TESTS)):
        if name.endswith(".py"):
            yield name


def _read(name):
    with io.open(os.path.join(TESTS, name), encoding="utf-8") as handle:
        return handle.read()


def test_every_module_that_imports_playwright_asks_pytest_to_skip_first():
    unguarded = []
    for name in _modules():
        source = _read(name)
        imported = TOP_LEVEL_IMPORT.search(source)
        if not imported:
            continue
        guard = GUARD.search(source)
        if guard is None or guard.start() > imported.start():
            line = source[: imported.start()].count("\n") + 1
            unguarded.append(f"{name}:{line}")
    assert not unguarded, (
        "these modules import Playwright before telling pytest to skip without "
        "it, so collection fails outright on a machine that has no browsers "
        '(add pytest.importorskip("playwright.sync_api") above the import): '
        + ", ".join(unguarded)
    )


def test_the_suite_still_has_browser_tests_to_guard():
    """
    If the pattern above is ever met by deleting the browser tests instead of
    guarding them, this says so rather than passing on an empty tree.
    """
    naming = [name for name in _modules() if TOP_LEVEL_IMPORT.search(_read(name))]
    assert len(naming) >= 20, f"only {len(naming)} modules drive a browser: {naming}"
