"""
Inox Hydra: Windows System Tray Controller & Background Daemon
==============================================================
Native Windows background tray controller using pure Python ctypes Win32 Shell API
(zero external C++ compilation dependencies).

Provides:
- Persistent system tray icon with tooltips.
- Context menu:
  1. Open Inox Hydra Studio (Borderless Chrome App Window).
  2. Open Chrome Sidepanel.
  3. Run Automated QA Tests.
  4. Restart Local Server.
  5. Exit.
- Server health supervision (auto-launches uvicorn if offline).
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
import subprocess
import threading
import webbrowser

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Win32 Constants
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002

# Menu Command IDs
ID_OPEN_STUDIO = 1001
ID_OPEN_SIDEPANEL = 1002
ID_RUN_TESTS = 1003
ID_RESTART_SERVER = 1004
ID_SEPARATOR = 1005
ID_EXIT = 1006

# Paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(PROJECT_ROOT, "studio", "extension", "icons", "icon-48.png")


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uID', wintypes.UINT),
        ('uFlags', wintypes.UINT),
        ('uCallbackMessage', wintypes.UINT),
        ('hIcon', wintypes.HICON),
        ('szTip', wintypes.WCHAR * 128),
        ('dwState', wintypes.DWORD),
        ('dwStateMask', wintypes.DWORD),
        ('szInfo', wintypes.WCHAR * 256),
        ('uTimeoutOrVersion', wintypes.UINT),
        ('szInfoTitle', wintypes.WCHAR * 64),
        ('dwInfoFlags', wintypes.DWORD),
        ('guidItem', ctypes.c_byte * 16),
        ('hBalloonIcon', wintypes.HICON)
    ]


class InoxHydraTray:
    """
    Native Win32 System Tray implementation for LinkedIn Studio Enterprise.
    """

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.shell32 = ctypes.windll.shell32
        self.kernel32 = ctypes.windll.kernel32

        self.hwnd = None
        self.server_process = None
        self.nid = None
        self.running = False

    def is_server_running(self) -> bool:
        """Checks if localhost port 8000 is listening."""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', 8000)) == 0

    def start_server_if_needed(self):
        """Launches backend uvicorn server in background if not already running."""
        if not self.is_server_running():
            print("[Tray] Starting local uvicorn server...")
            try:
                self.server_process = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "studio.backend.app:app", "--host", "127.0.0.1", "--port", "8000"],
                    cwd=PROJECT_ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(1.5)
            except Exception as e:
                print(f"[Tray] Error launching server: {e}")

    def open_studio(self):
        """Launches Chrome in borderless app window, falling back to default browser."""
        self.start_server_if_needed()
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
        for cp in chrome_paths:
            if os.path.exists(cp):
                try:
                    subprocess.Popen([cp, '--app=http://127.0.0.1:8000', '--window-size=1440,920'])
                    return
                except Exception:
                    pass
        webbrowser.open("http://127.0.0.1:8000")

    def open_sidepanel(self):
        """Directs to CRM tab or LinkedIn extension guidance."""
        webbrowser.open("http://127.0.0.1:8000#tab-inbox")

    def run_tests(self):
        """Executes full automated test suite in a detached thread."""
        def _execute():
            print("[Tray] Running test suites...")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-v"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True
            )
            print("[Tray] Test results:\n", result.stdout)

        threading.Thread(target=_execute, daemon=True).start()

    def restart_server(self):
        """Restarts local uvicorn server."""
        print("[Tray] Restarting local server...")
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=2)
            except Exception:
                pass
        self.start_server_if_needed()

    def exit_app(self):
        """Removes tray icon and terminates background processes."""
        print("[Tray] Exiting Inox Hydra Tray...")
        self.running = False
        if self.nid and self.hwnd:
            self.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
        if self.hwnd:
            self.user32.PostQuitMessage(0)

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        """Window message callback handling tray events and context menus."""
        if msg == WM_TRAYICON:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONDBLCLK):
                if lparam == WM_LBUTTONDBLCLK:
                    self.open_studio()
                    return 0

                # Show Context Menu
                pt = wintypes.POINT()
                self.user32.GetCursorPos(ctypes.byref(pt))

                hmenu = self.user32.CreatePopupMenu()
                self.user32.AppendMenuW(hmenu, MF_STRING, ID_OPEN_STUDIO, "🚀 Open Inox Hydra Studio")
                self.user32.AppendMenuW(hmenu, MF_STRING, ID_OPEN_SIDEPANEL, "📱 Open Inbound CRM")
                self.user32.AppendMenuW(hmenu, MF_STRING, ID_RUN_TESTS, "🧪 Run Automated QA Tests")
                self.user32.AppendMenuW(hmenu, MF_STRING, ID_RESTART_SERVER, "🔄 Restart Local Server")
                self.user32.AppendMenuW(hmenu, MF_SEPARATOR, ID_SEPARATOR, "")
                self.user32.AppendMenuW(hmenu, MF_STRING, ID_EXIT, "❌ Exit Inox Hydra")

                self.user32.SetForegroundWindow(hwnd)
                self.user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None)
                self.user32.DestroyMenu(hmenu)
                return 0

        elif msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == ID_OPEN_STUDIO:
                self.open_studio()
            elif cmd == ID_OPEN_SIDEPANEL:
                self.open_sidepanel()
            elif cmd == ID_RUN_TESTS:
                self.run_tests()
            elif cmd == ID_RESTART_SERVER:
                self.restart_server()
            elif cmd == ID_EXIT:
                self.exit_app()
            return 0

        elif msg == WM_DESTROY:
            self.exit_app()
            return 0

        return self.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def create_tray(self):
        """Creates hidden Win32 window and adds notification icon to the system tray."""
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self._wndproc_cb = WNDPROC(self.wnd_proc)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.UINT),
                ('style', wintypes.UINT),
                ('lpfnWndProc', WNDPROC),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE),
                ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE),
                ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR),
                ('lpszClassName', wintypes.LPCWSTR),
                ('hIconSm', wintypes.HICON)
            ]

        class_name = "InoxHydraTrayClass"
        wndclass = WNDCLASSEXW()
        wndclass.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wndclass.lpfnWndProc = self._wndproc_cb
        wndclass.hInstance = self.kernel32.GetModuleHandleW(None)
        wndclass.lpszClassName = class_name

        self.user32.RegisterClassExW(ctypes.byref(wndclass))

        self.hwnd = self.user32.CreateWindowExW(
            0, class_name, "Inox Hydra Tray Window",
            0, 0, 0, 0, 0,
            None, None, wndclass.hInstance, None
        )

        # Standard application default icon
        IDI_APPLICATION = 32512
        hicon = self.user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))

        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP | NIF_INFO
        self.nid.uCallbackMessage = WM_TRAYICON
        self.nid.hIcon = hicon
        self.nid.szTip = "Inox Hydra: LinkedIn Studio Enterprise (127.0.0.1:8000)"
        self.nid.szInfo = "Inox Hydra Studio daemon active on localhost:8000."
        self.nid.szInfoTitle = "LinkedIn Studio Enterprise"
        self.nid.dwInfoFlags = 1  # NIIF_INFO

        self.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        self.running = True

    def run(self):
        """Starts server and runs standard Win32 message pump."""
        self.start_server_if_needed()
        self.create_tray()
        print("[Tray] Inox Hydra background tray active on 127.0.0.1:8000.")

        msg = wintypes.MSG()
        while self.running and self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))


def verify_tray_setup() -> bool:
    """Non-blocking validation test for CI/QA."""
    tray = InoxHydraTray()
    assert tray.user32 is not None
    assert tray.shell32 is not None
    assert ctypes.sizeof(NOTIFYICONDATAW) == 976
    return True


if __name__ == "__main__":
    if "--test" in sys.argv:
        try:
            assert verify_tray_setup()
            print("✅ Inox Hydra Tray Win32 ctypes verification passed.")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Tray verification failed: {e}", file=sys.stderr)
            sys.exit(1)

    tray = InoxHydraTray()
    tray.run()
