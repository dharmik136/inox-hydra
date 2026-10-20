"""
The install, update and uninstall instructions describe what a Windows user
does today, and macOS and Linux from source. [INS-16]

README's Install section said "The studio opens in its own window" (only with
Chrome), had no Unblock step, no word on port 8000, an upgrade that skipped the
extension and the shortcut, and no path at all for macOS or Linux; the help
told portable users that the launcher does not check that the server started
and that the shortcut script does not work there. Both stopped being true in
this batch, so the words are held to the code: every launcher message the
docs quote is one the code prints.

Strict Invariants:
- Zero em-dashes.
"""

import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HELP = os.path.join(REPO_ROOT, "docs", "help")


def _read(*parts):
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _install_section():
    readme = _read("README.md")
    start = readme.index("## 📦 Install")
    return readme[start:readme.index("\n---", start)]


def test_the_readme_walks_a_windows_user_through_today():
    section = _install_section()
    for needed in ("InoxHydra-<version>-win64.zip", "Unblock", "InoxHydra.bat", "Inox Hydra Engine",
                   "8001 to 8009", "only connects on port 8000", "create_desktop_shortcut.vbs",
                   "backup --all", "reload the browser extension", "To remove it"):
        assert needed in section, f"the Install section does not cover {needed!r}"
    assert "The studio opens in its own window." not in section


def test_the_readme_gives_macos_and_linux_a_path():
    section = _install_section()
    assert "### macOS and Linux: run from source for now" in section
    assert "./launch_studio.sh" in section
    assert "npm --prefix studio/ui run build" in section


def test_the_help_no_longer_says_the_portable_launcher_does_not_check():
    first_run = _read("docs", "help", "open-the-studio-for-the-first-time.md")
    assert "The launcher does not check that the server actually started." not in first_run
    assert "### If port 8000 is taken" in first_run
    desktop = _read("docs", "help", "put-the-studio-on-your-desktop.md")
    assert "but it does not work there" not in desktop


def test_the_update_and_removal_steps_are_complete():
    update = _read("docs", "help", "check-your-version-and-update-the-studio.md")
    assert "after-an-update-reload-the-extension.md" in update
    assert "backup --all" in update and "Unblock" in update
    remove = _read("docs", "help", "remove-the-studio-from-this-computer.md")
    assert "**Installed apps**" in remove
    assert "There is no uninstaller or uninstall command" not in remove


def test_every_launcher_message_the_docs_quote_is_one_the_code_prints():
    from studio.backend import desktop  # noqa: F401  (imported so a rename breaks here)

    code = _read("studio", "backend", "desktop.py")
    vbs = _read("create_desktop_shortcut.vbs")
    quoted = {
        "is in use by another program, not Inox Hydra.": code,
        "The studio engine stopped while it was starting.": code,
        "The studio is ready at": code,
        "Shortcut created on Desktop, pointing at:": vbs,
        "Could not find InoxHydra.bat or launch_studio.bat next to this script.": vbs,
    }
    docs = "".join(_read("docs", "help", name) for name in (
        "open-the-studio-for-the-first-time.md", "the-studio-will-not-open.md",
        "put-the-studio-on-your-desktop.md"))
    for message, source in quoted.items():
        assert message in docs, f"the help no longer quotes {message!r}"
        assert message in source, f"the help quotes {message!r}, which nothing prints"
