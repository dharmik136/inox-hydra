"""
Any set of test files runs together.
====================================

Several test files put tools/ first on sys.path when they are imported, and
tools/library_bundle.py, the vendor's signing command, then shadowed the
backend's library_bundle for any test that imported the app after them:
tests/test_privacy_page_is_the_policy.py and then a bot test, or
tests/test_licensing.py and then a bot test, errored with "module
'library_bundle' has no attribute 'MAX_BYTES'". The full suite never met it,
because an earlier file imports the app first, so it showed only when a
hand-picked set of files ran together. Each pair here runs in a process of
its own, with a home of its own, in the order that failed.

docs/quality/cycle4/bot-phase6.md, item 0.

Strict Invariants:
- Zero em-dashes.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# A bot test whose fixture imports the app, as every bot test does.
IMPORTS_THE_APP = "tests/test_telegram_bot_commands.py::test_a_command_it_does_not_know_says_how_to_see_what_it_does"


def _run_together(tmp_path, *tests):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, INOX_HYDRA_HOME=str(home))
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300)
    return done.returncode, (done.stdout + done.stderr)[-3000:]


@pytest.mark.parametrize("first", [
    # Puts tools/ first while it runs, to load the privacy page's renderer.
    "tests/test_privacy_page_is_the_policy.py::test_the_renderer_refuses_what_it_does_not_understand",
    # Puts tools/ first when it is imported.
    "tests/test_licensing.py::test_verify_answers_false_on_garbage",
])
def test_a_file_that_puts_tools_first_leaves_the_backends_library_bundle_alone(tmp_path, first):
    code, said = _run_together(tmp_path, first, IMPORTS_THE_APP)
    assert code == 0, said
    assert "2 passed" in said, said
