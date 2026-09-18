"""
Portable Distributable Builder: A ZIP A Stranger Can Double Click.
==================================================================
Produces a self-contained Windows folder that runs Inox Hydra with no Python
installed, no installer, and no administrator rights.

Layout of the produced artifact:

    InoxHydra-<version>-win64/
        runtime/        CPython embeddable distribution
        lib/            vendored third party dependencies
        app/studio/     the application package
        extension/      unpacked Chrome MV3 source
        InoxHydra.bat   launcher
        README.txt      quick start

Why the embeddable distribution rather than PyInstaller: an unsigned PyInstaller
bootloader trips antivirus heuristics, and there is no support channel to walk a
user through a quarantine on a machine nobody can reach. An extracted folder of
ordinary files does not have that problem.

IMPORTANT: `app/studio/` deliberately ships without a `data/` directory. Its
absence is what makes `paths.get_app_home()` resolve to the user profile, which
is what allows an update to replace this entire folder without destroying the
user's drafts and leads. Do not add one.

Usage:
    python tools/build_portable.py [--skip-download]

Strict Invariants:
- Zero em-dashes.
- The building interpreter must match the embedded runtime's version, because
  compiled wheels are ABI specific.
"""

import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD_ROOT = os.path.join(REPO_ROOT, "dist", "portable")
CACHE_DIR = os.path.join(REPO_ROOT, "build_artifacts", "runtime_cache")

PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
PYTHON_TAG = f"{sys.version_info.major}{sys.version_info.minor}"
EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)

# Copied into app/studio/. Everything else in studio/ is either user state,
# test code, or build tooling, none of which belongs in a user artifact.
STUDIO_EXCLUDE = {"data", "assets", "tests", "__pycache__", ".pytest_cache"}

LAUNCHER = r"""@echo off
title Inox Hydra - LinkedIn Studio
cd /d "%~dp0"

echo ==========================================================
echo   Inox Hydra - Local Creator Engine
echo   100%% local. Zero cloud egress. Port 8000.
echo ==========================================================
echo.

:: Already running? Reuse the existing server rather than starting a second.
powershell -NoProfile -Command "$c = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue; if ($c) { exit 0 } else { exit 1 }" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [*] Already running on http://127.0.0.1:8000
) else (
    echo [*] Starting local engine...
    start /min "Inox Hydra Engine" "%~dp0runtime\python.exe" -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8000
    timeout /t 4 /nobreak >nul
)

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

if exist %CHROME% (
    echo [*] Opening the studio...
    start "" %CHROME% --app="http://127.0.0.1:8000" --window-size=1440,920
) else (
    echo [*] Chrome not found. Opening your default browser instead.
    start http://127.0.0.1:8000
)

echo [*] Ready.
exit /b 0
"""

CLI_LAUNCHER = r"""@echo off
:: Inox Hydra support toolkit.
::
:: Examples:
::   InoxHydra-CLI.bat doctor --bundle
::   InoxHydra-CLI.bat backup
::   InoxHydra-CLI.bat export --format csv
::   InoxHydra-CLI.bat update status
::
:: Run with no arguments to list every command.
cd /d "%~dp0"
if "%~1"=="" (
    "%~dp0runtime\python.exe" -m studio.cli --help
) else (
    "%~dp0runtime\python.exe" -m studio.cli %*
)
"""

README = """Inox Hydra - LinkedIn Studio (Portable)
=======================================

QUICK START
-----------
1. Extract this folder anywhere you like. A USB stick is fine.
2. Double click InoxHydra.bat.
3. The studio opens in its own window.

No Python installation is required. Nothing is sent to any server.


WHERE YOUR DATA LIVES
---------------------
Your drafts, leads, analytics and generated media are stored in:

    %LOCALAPPDATA%\\InoxHydra

They are deliberately kept OUTSIDE this folder so that upgrading, by replacing
this folder with a newer one, never touches your work.

A timestamped backup of your database is taken automatically before any schema
upgrade, in:

    %LOCALAPPDATA%\\InoxHydra\\backups


TRUE PORTABLE MODE (optional)
-----------------------------
To keep your data inside this folder instead, so it travels with the USB stick,
create an empty folder named "data" inside app\\studio\\ before first launch.

Be aware that replacing the folder to upgrade will then also replace your data,
so take your own copies first.

You can also point the application anywhere by setting INOX_HYDRA_HOME.


UPGRADING
---------
1. Download the newer ZIP.
2. Delete this folder.
3. Extract the new one.

Your data is untouched, and any database schema changes are applied
automatically on first launch.


CHROME EXTENSION
----------------
The extension/ folder contains the browser bridge. Install it from the Chrome
Web Store link in the documentation rather than loading it unpacked. Recent
Chrome versions disable unpacked and sideloaded extensions after a browser
update, so a store install is the only version that keeps working.


SUPPORT TOOLKIT
---------------
Everything runs locally, so we cannot see errors on your machine. Use
InoxHydra-CLI.bat to look after your own installation:

    InoxHydra-CLI.bat doctor --bundle    health report, safe to post publicly
    InoxHydra-CLI.bat backup             snapshot database and media
    InoxHydra-CLI.bat restore <zip>      roll back to a snapshot
    InoxHydra-CLI.bat export             take your content elsewhere
    InoxHydra-CLI.bat reset              fix a broken setup, keeping your content
    InoxHydra-CLI.bat update status      see whether update checks are on

The diagnostics bundle redacts your LinkedIn session and any API keys, so it is
safe to attach to a public issue. Open it in a text editor to confirm.


UPDATE CHECKS
-------------
Off by default. Nothing is sent anywhere unless you turn them on with:

    InoxHydra-CLI.bat update enable

Even then, the check only downloads a small version file and tells you whether a
newer release exists. It never installs anything by itself.
"""


def log(step, message):
    print(f"[{step}] {message}")


def fetch_runtime(skip_download=False):
    """Downloads the embeddable CPython, caching it between builds."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cached = os.path.join(CACHE_DIR, f"python-{PYTHON_VERSION}-embed-amd64.zip")

    if os.path.exists(cached) and os.path.getsize(cached) > 0:
        log("runtime", f"using cached {os.path.basename(cached)}")
        return cached
    if skip_download:
        raise SystemExit(f"--skip-download was passed but no cached runtime exists at {cached}")

    log("runtime", f"downloading {EMBED_URL}")
    urllib.request.urlretrieve(EMBED_URL, cached)
    log("runtime", f"downloaded {os.path.getsize(cached):,} bytes")
    return cached


def write_path_file(runtime_dir):
    """
    Rewrites python3XX._pth so the embedded interpreter can see our code.

    Paths are resolved relative to the directory holding python.exe. `import
    site` must be enabled, because pip installed distributions rely on it.
    """
    pth = os.path.join(runtime_dir, f"python{PYTHON_TAG}._pth")
    content = "\n".join([
        f"python{PYTHON_TAG}.zip",
        ".",
        "..\\lib",
        "..\\app",
        "",
        "# site is required so that pip installed distributions are importable.",
        "import site",
        "",
    ])
    with open(pth, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    log("runtime", f"wrote {os.path.basename(pth)} with lib/ and app/ on the path")


def vendor_dependencies(lib_dir):
    """
    Installs runtime dependencies into lib/ as a flat directory.

    Uses the building interpreter, so the compiled wheels match the embedded
    runtime's ABI. main() asserts those versions agree before we get here.
    """
    log("deps", "installing runtime dependencies into lib/")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install",
         "--quiet", "--no-compile", "--target", lib_dir,
         "--no-warn-script-location", REPO_ROOT],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-3000:])
        print(result.stderr[-3000:])
        raise SystemExit("dependency vendoring failed")

    # pip installs our own package into lib/ as well. app/ carries the real
    # copy, so remove the duplicate to avoid two importable copies of studio.
    for name in ("studio", "inox_hydra"):
        for entry in os.listdir(lib_dir):
            if entry == name or entry.startswith(name + "-"):
                target = os.path.join(lib_dir, entry)
                shutil.rmtree(target) if os.path.isdir(target) else os.remove(target)
    log("deps", f"vendored {len(os.listdir(lib_dir))} entries")


def copy_application(app_dir):
    """Copies the studio package, excluding user state, tests and caches."""
    target = os.path.join(app_dir, "studio")
    shutil.copytree(
        os.path.join(REPO_ROOT, "studio"), target,
        ignore=shutil.ignore_patterns(*STUDIO_EXCLUDE, "*.pyc", "*.db", "*.db-wal", "*.db-shm"),
    )
    # The data directory's ABSENCE is what selects user-profile state. Assert it.
    assert not os.path.exists(os.path.join(target, "data")), (
        "app/studio/data exists in the artifact. That would make the build write "
        "user state inside the install directory, so an update would destroy it."
    )
    log("app", f"copied studio package, {sum(len(f) for _, _, f in os.walk(target))} files")
    return target


def main():
    skip_download = "--skip-download" in sys.argv

    if platform.system() != "Windows":
        log("warn", "building a Windows artifact from a non-Windows host. "
                    "Compiled wheels will be wrong. Use a windows runner.")

    log("prep", "staging bundled content and propagating version")
    if subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tools", "prepare_package.py")],
                      cwd=REPO_ROOT).returncode != 0:
        raise SystemExit("prepare_package failed")

    sys.path.insert(0, REPO_ROOT)
    from studio.__version__ import __version__

    name = f"InoxHydra-{__version__}-win64"
    staging = os.path.join(BUILD_ROOT, name)
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    log("prep", f"building {name}")

    runtime_zip = fetch_runtime(skip_download)
    runtime_dir = os.path.join(staging, "runtime")
    os.makedirs(runtime_dir)
    with zipfile.ZipFile(runtime_zip) as z:
        z.extractall(runtime_dir)
    embedded = os.path.join(runtime_dir, "python.exe")
    assert os.path.exists(embedded), "embeddable runtime is missing python.exe"
    write_path_file(runtime_dir)

    lib_dir = os.path.join(staging, "lib")
    os.makedirs(lib_dir)
    vendor_dependencies(lib_dir)

    app_dir = os.path.join(staging, "app")
    os.makedirs(app_dir)
    copy_application(app_dir)

    shutil.copytree(os.path.join(REPO_ROOT, "studio", "extension"),
                    os.path.join(staging, "extension"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "package_extension.py"))
    log("app", "copied unpacked extension for store submission and fallback")

    with open(os.path.join(staging, "InoxHydra.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(LAUNCHER)
    with open(os.path.join(staging, "InoxHydra-CLI.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(CLI_LAUNCHER)
    with open(os.path.join(staging, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(README)

    shutil.copy2(os.path.join(REPO_ROOT, "create_desktop_shortcut.vbs"), staging)
    shutil.copy2(os.path.join(REPO_ROOT, "LICENSE"), staging)

    log("zip", "compressing")
    archive = os.path.join(BUILD_ROOT, name + ".zip")
    if os.path.exists(archive):
        os.remove(archive)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, filenames in os.walk(staging):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                z.write(full, os.path.join(name, os.path.relpath(full, staging)))

    extracted = sum(
        os.path.getsize(os.path.join(d, f))
        for d, _, fs in os.walk(staging) for f in fs
    )
    log("done", f"{archive}")
    log("done", f"compressed {os.path.getsize(archive) / 1024 / 1024:.1f} MB, "
                f"extracted {extracted / 1024 / 1024:.1f} MB")
    print()
    print(f"Artifact: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
