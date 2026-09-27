"""
The one-click launch has to attach the bridge on the ordinary Windows path.
===========================================================================

Audit W19. Edge already running with the creator's normal profile receives a
relaunch as a request to open a tab and drops --load-extension, so "Open
LinkedIn with the bridge" opened LinkedIn with no bridge, and Setup's first
step never ticked. A separate --user-data-dir is a separate browser instance,
which always honours the flag.

That profile holds the creator's LinkedIn login, which makes where it lives a
security question: the build copies studio/ from the working tree, so a
profile there would ship a logged-in session inside the next build.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import browser_launcher
import paths

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def captured(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls.append(list(args))

    monkeypatch.setattr(browser_launcher.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(browser_launcher, "detect_installed_browsers", lambda: {
        "edge": {"id": "edge", "name": "Microsoft Edge", "path": r"C:\Program Files\Edge\msedge.exe"},
    })
    return calls


def test_the_launch_uses_a_dedicated_profile(captured):
    browser_launcher.launch_browser_with_extension("edge", "https://www.linkedin.com/in/me/")
    args = captured[0]
    profile = [a for a in args if a.startswith("--user-data-dir=")]
    assert profile, "without its own profile the launch hands off to a running Edge and loses the bridge"
    assert any(a.startswith("--load-extension=") for a in args)


def test_the_studio_opens_beside_linkedin(captured):
    """The extension's access token is set only by loading the studio in this same profile."""
    browser_launcher.launch_browser_with_extension("edge", "https://www.linkedin.com/in/me/")
    args = captured[0]
    assert "https://www.linkedin.com/in/me/" in args
    assert browser_launcher.STUDIO_TAB_URL in args


def test_the_profile_never_lives_in_the_tree(monkeypatch):
    """Even in a source or portable install, where every other kind of state does."""
    monkeypatch.delenv("INOX_HYDRA_HOME", raising=False)
    # Resolve the path without creating it on the machine running the tests.
    monkeypatch.setattr(paths, "_ensure", lambda path: path)
    studio_dir = os.path.join(REPO_ROOT, "studio")
    for browser in ("edge", "brave"):
        location = os.path.abspath(paths.get_browser_profile_dir(browser))
        assert not location.startswith(os.path.abspath(studio_dir) + os.sep), (
            f"the {browser} profile would be at {location}, inside the tree the build copies"
        )


def test_a_browser_id_cannot_steer_the_profile_path():
    location = paths.get_browser_profile_dir("../../etc")
    assert ".." not in os.path.relpath(location, os.path.dirname(os.path.dirname(location)))


def test_the_build_refuses_a_browser_session_store():
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import build_portable

    for name in ("cookies", "login data", "web data"):
        assert name in build_portable.ALWAYS_SECRET, f"a Chromium {name} file would not stop the build"
