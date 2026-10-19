"""
The Tray's Exit Stops the Studio It Started.
============================================

"Exit Inox Hydra" removed the tray icon and left the server the tray had
started running with nothing on screen, still dispatching the queue, and the
help could only point at Task Manager. These run off Windows with a fake
process, since the Win32 calls themselves are not what is under test.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import re
import sys
import types

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

import studio_tray  # noqa: E402


class FakeServer:
    def __init__(self, running=True):
        self.running = running
        self.terminated = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.running = False


def _tray(server):
    tray = studio_tray.InoxHydraTray.__new__(studio_tray.InoxHydraTray)
    quits = []
    tray.user32 = types.SimpleNamespace(PostQuitMessage=lambda code: quits.append(code))
    tray.shell32 = types.SimpleNamespace(Shell_NotifyIconW=lambda *a: None)
    tray.kernel32 = None
    tray.hwnd = 1
    tray.nid = None
    tray.running = True
    tray.server_process = server
    return tray, quits


def test_exit_stops_the_server_the_tray_started():
    server = FakeServer()
    tray, quits = _tray(server)
    tray.exit_app()
    assert server.terminated, "Exit left the tray's own server running with no window"
    assert quits == [0] and tray.running is False


def test_exit_leaves_a_server_it_did_not_start_alone():
    tray, quits = _tray(None)
    tray.exit_app()
    assert quits == [0]


def test_a_server_that_already_stopped_is_not_signalled():
    server = FakeServer(running=False)
    tray, _ = _tray(server)
    tray.exit_app()
    assert server.terminated is False


def test_the_creator_menu_has_no_developer_test_runner():
    with open(os.path.join(REPO_ROOT, "studio_tray.py"), encoding="utf-8") as handle:
        source = handle.read()
    menu_lines = [line for line in source.splitlines() if "AppendMenuW" in line]
    assert menu_lines, "the menu could not be found"
    assert not [line for line in menu_lines if re.search(r"ID_RUN_TESTS|QA Tests", line)]
