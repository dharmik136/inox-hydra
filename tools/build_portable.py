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

# Directories under studio/ that hold the BUILDER's own state rather than the
# product. In a source checkout paths.get_app_home() resolves to studio/,
# because studio/data exists, so the creator's database, backups, logs and
# credential vault all materialise inside the tree that copy_application walks.
#
# backups/ is the one that mattered: support.create_backup() writes a zip there
# containing the whole database plus every uploaded and generated image. Three
# pre-migration database files sitting there right now hold 225 real leads and
# 842 real interactions. Only the *.db pattern kept them out of the artifact,
# and a .zip written by the documented `InoxHydra-CLI.bat backup` command would
# not have matched it.
STUDIO_EXCLUDE = {
    "data", "assets", "tests", "__pycache__", ".pytest_cache",
    "backups", "logs", "vault",
}

# Secrets that must never leave this machine inside an artifact.
#
# studio/extension.pem is the key that signs extension updates. Every installed
# copy accepts an update signed with it as genuine, so shipping it hands any
# recipient the ability to push code to every other user.
#
# tests/test_distribution_hygiene.py already refuses to let git track these, and
# it is explicit that it checks the index rather than the working tree. That is
# the right boundary for git and the wrong one for a build: copy_application
# reads the working tree, so a file that is correctly gitignored and correctly
# absent from CI is still sitting next to the source on the machine of whoever
# generated it, and was being copied straight into the distributable.
SECRET_PATTERNS = (
    "*.pem", "*.key", "*.pfx", "*.p12", "*.crx",
    "*.env", ".env", ".env.*",
    "id_rsa", "id_rsa.*", "*.asc",
)


# Names that are a credential whatever is inside them.
ALWAYS_SECRET = (
    "*.pfx", "*.p12", "*.env", ".env", ".env.*", "id_rsa", "id_rsa.*",
    # The local API bearer token. It has no extension, so every pattern that
    # works by suffix misses it, and it is matched by name instead.
    "*.token", "api_token",
)

# Markers that make a PEM a private key rather than a public certificate.
#
# This distinction has to be drawn on content, not on the extension. lib/certifi
# ships cacert.pem, which is the public trust root bundle every HTTPS request
# depends on, and refusing to ship it would break the product. The extension
# signing key has the same extension and must never ship. Only the bytes tell
# them apart.
PRIVATE_KEY_MARKERS = (
    b"PRIVATE KEY",
    b"BEGIN OPENSSH PRIVATE KEY",
    b"BEGIN PGP PRIVATE KEY",
)


def assert_no_secrets(staged_root):
    """
    Refuses to produce an artifact carrying a credential.

    A second check rather than trusting the ignore patterns, because the cost
    of being wrong is unbounded and the cost of the check is a directory walk.
    Raises rather than warning: a build that prints a warning nobody reads and
    then writes the ZIP anyway has not prevented anything.
    """
    import fnmatch

    found = []
    for root, _dirs, files in os.walk(staged_root):
        for name in files:
            relative = os.path.relpath(os.path.join(root, name), staged_root)
            lowered = name.lower()

            if any(fnmatch.fnmatch(lowered, pattern) for pattern in ALWAYS_SECRET):
                found.append(f"{relative} (credential file)")
                continue

            # Certificate shaped files are judged on their contents.
            if lowered.endswith((".pem", ".key", ".asc", ".crt")):
                try:
                    with open(os.path.join(root, name), "rb") as handle:
                        head = handle.read(65536)
                except OSError:
                    continue
                if any(marker in head for marker in PRIVATE_KEY_MARKERS):
                    found.append(f"{relative} (contains a private key)")

    if found:
        raise SystemExit(
            "REFUSING TO BUILD. The staged artifact contains credentials:\n  "
            + "\n  ".join(found)
            + "\n\nThese would ship to every person who installs this build. "
              "Remove them from the source tree, or exclude them from the copy."
        )

LAUNCHER = r"""@echo off
title Inox Hydra - LinkedIn Studio
cd /d "%~dp0"

echo ==========================================================
echo   Inox Hydra - Local Creator Engine
echo   100%% local. Zero cloud egress. Port 8000.
echo ==========================================================
echo.

:: The maintainer surface stays off. devtools.is_dev_mode() treats the absence
:: of this variable as off already, so this line is belt and braces: it also
:: clears a value inherited from the shell that launched this one, which is the
:: only way a shipped folder could otherwise come up with the element picker and
:: the annotation ledger visible to a paying creator.
set INOX_DEV_MODE=

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
1. BEFORE extracting: right click the downloaded ZIP, choose Properties, tick
   "Unblock" near the bottom, then click OK. See the next section for why.
2. Extract the folder anywhere you like. A USB stick is fine.
3. Double click InoxHydra.bat.
4. The studio opens in its own window.

No Python installation is required. Nothing is sent to any server.


IF WINDOWS BLOCKS IT
--------------------
This is expected, and it is not a sign that anything is wrong.

Windows attaches a "downloaded from the internet" mark to every file inside a
ZIP you download. This software is not code signed, because a signing
certificate costs several hundred dollars a year and this is a local tool that
never talks to a server. So Windows treats it with suspicion.

What you may see, and what to do:

  "Windows protected your PC" (blue SmartScreen box)
      Click "More info", then "Run anyway".

  The launcher opens and closes instantly, or nothing happens
      The Unblock step in Quick Start was most likely skipped. Delete the
      extracted folder, tick Unblock on the original ZIP, and extract again.
      Unblocking the ZIP before extracting clears every file inside at once.

  Your antivirus quarantines runtime\\python.exe
      A false positive on an unsigned Python interpreter. Restore it and add an
      exclusion for the folder, or ask whoever sent you this for a copy through
      a different channel.

Everything in this folder is ordinary files. You can inspect any of it: the
application is plain Python source under app\\studio\\, readable in Notepad.


IF IT STILL WILL NOT START
--------------------------
  Something else is using port 8000
      Close the other application, or close any earlier copy of Inox Hydra
      still running in the background, then try again.

  Chrome is not installed
      Not a problem. The studio opens in your default browser instead. It will
      look like a normal tab rather than its own window.

  Anything else
      Run InoxHydra-CLI.bat doctor --bundle and send the resulting file to
      whoever gave you this. It redacts passwords and keys, and it tells them
      exactly what went wrong on your machine, which they otherwise cannot see.


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
    """Copies the studio package, excluding user state, tests, caches and secrets."""
    target = os.path.join(app_dir, "studio")
    shutil.copytree(
        os.path.join(REPO_ROOT, "studio"), target,
        ignore=shutil.ignore_patterns(
            *STUDIO_EXCLUDE, "*.pyc", "*.db", "*.db-wal", "*.db-shm",
            # A backup zip carries the entire database and media tree, and a
            # diagnostics json carries the environment report. Both are written
            # by documented commands into directories excluded above, so these
            # are the second line rather than the first.
            "*.zip", "*.log", "*.token",
            *SECRET_PATTERNS,
        ),
    )
    # The data directory's ABSENCE is what selects user-profile state. Assert it.
    assert not os.path.exists(os.path.join(target, "data")), (
        "app/studio/data exists in the artifact. That would make the build write "
        "user state inside the install directory, so an update would destroy it."
    )
    assert_no_secrets(target)
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
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc", "package_extension.py",
                        *SECRET_PATTERNS, *ALWAYS_SECRET))
    log("app", "copied unpacked extension for store submission and fallback")

    with open(os.path.join(staging, "InoxHydra.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(LAUNCHER)
    with open(os.path.join(staging, "InoxHydra-CLI.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(CLI_LAUNCHER)
    with open(os.path.join(staging, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(README)

    shutil.copy2(os.path.join(REPO_ROOT, "create_desktop_shortcut.vbs"), staging)
    shutil.copy2(os.path.join(REPO_ROOT, "LICENSE"), staging)

    # The application icon. Shipped at the staging root, beside the launcher,
    # because that is what the shortcut and the tray both resolve against. Its
    # absence is why this product wore the generic Windows icon, so the build
    # refuses rather than quietly producing that artifact again.
    icon_source = os.path.join(REPO_ROOT, "assets", "inox_hydra.ico")
    assert os.path.isfile(icon_source), (
        "assets/inox_hydra.ico is missing. Run tools/generate_icons.py before building, "
        "or the shipped artifact falls back to the generic Windows application icon."
    )
    os.makedirs(os.path.join(staging, "assets"), exist_ok=True)
    shutil.copy2(icon_source, os.path.join(staging, "assets", "inox_hydra.ico"))
    log("app", "copied the application icon")

    # Everything, immediately before the zip is written.
    #
    # copy_application checks what it copied, but four more trees are staged
    # after it returns: the runtime, the vendored lib directory, the unpacked
    # extension and the loose root files. A check that covers one of five is
    # not a check, and the argument it is given is the part a grep over source
    # text cannot verify.
    assert_no_secrets(staging)

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
