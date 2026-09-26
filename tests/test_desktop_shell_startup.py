"""
The desktop shell must not be able to die before it opens.
=========================================================

A release build of the Tauri shell has no console. A panic during setup is
therefore an application that does not open and says nothing, and the user's
only evidence is a shortcut that appears to do nothing.

The tray was the route to that. build_tray ran as `build_tray(app)?` before the
engine started, and fetched its icon with `.unwrap()`, so a missing icon or a
Linux desktop with no appindicator library aborted setup and the `.expect` on
the builder turned it into a panic.

The shell's Rust is compiled in CI and never executed by a test, so these read
the source. They pin the shape of the fix rather than every line of it:

  the tray's failure is handled rather than propagated,
  the icon is not unwrapped,
  and close-to-hide depends on a tray existing, because hiding a window with no
  tray to bring it back strands the engine behind nothing the user can reach.
"""

import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_RS = os.path.join(REPO_ROOT, "desktop", "src-tauri", "src", "lib.rs")


def _code():
    if not os.path.exists(LIB_RS):
        pytest.skip("the desktop shell is not present in this checkout")
    with open(LIB_RS, encoding="utf-8") as handle:
        source = handle.read()
    # Comments explain the old shape and necessarily quote it.
    source = re.sub(r"//[^\n]*", "", source)
    return source


def test_a_tray_failure_does_not_abort_setup():
    code = _code()
    assert not re.search(r"build_tray\(\s*app\s*\)\s*\?", code), (
        "the tray's failure is propagated out of setup again, so any tray error "
        "becomes a silent panic in a release build"
    )
    assert re.search(r"match\s+build_tray\(", code), (
        "the tray outcome is no longer handled explicitly"
    )


def test_the_tray_icon_is_not_unwrapped():
    code = _code()
    assert not re.search(r"default_window_icon\(\)\s*\.unwrap\(\)", code), (
        "the tray icon is unwrapped, so a bundle without one panics at launch"
    )


def test_closing_hides_only_when_a_tray_can_bring_it_back():
    code = _code()
    close = re.search(r"CloseRequested.*?\n\s*\}\n\s*\}", code, re.DOTALL)
    assert close, "the close handler has moved"
    body = close.group(0)
    assert "TrayState" in body and "prevent_close" in body, (
        "close-to-hide no longer checks for a tray. Without one the hidden "
        "window cannot be reopened and the engine runs on behind it"
    )
