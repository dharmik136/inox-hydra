"""
Portable Distributable Builder: A ZIP A Stranger Can Double Click.
==================================================================
Produces a self-contained folder that runs Inox Hydra with no Python
installed, no installer, and no administrator rights.

Layout of the produced artifact:

    InoxHydra-<version>-<platform>/
        runtime/        CPython embeddable or standalone distribution
        lib/            vendored third party dependencies
        app/studio/     the application package
        extension/      unpacked Chrome MV3 source
        InoxHydra.*     launcher
        README.txt      quick start

Cross-Platform Runtime Packaging Decision:
------------------------------------------
On Windows, python.org publishes an official embeddable zip distribution. That
layout does not exist on macOS or Linux.

We evaluated four possible approaches for macOS and Linux:

1. PyInstaller / single-file freezing:
   REJECTED. An unsigned PyInstaller bootloader trips antivirus heuristics, and
   there is no support channel to walk a stranger through a quarantine. On
   macOS, PyInstaller bundles trigger Gatekeeper scrutiny and slow down launch
   by unpacking to temporary directories. Packaging opaque binaries also
   prevents auditing staged files for accidental credential leaks prior to
   installer packaging.

2. Relying on host system Python (/usr/bin/python3):
   REJECTED. macOS Monterey and newer do not ship with Python 3 (only a stub
   triggering an Xcode CLI tools dialog). Linux distributions ship disparate
   Python versions (3.10 through 3.13) and PEP 668 prevents pip vendoring
   without system disruption. Requiring creators to install and configure
   Python violates the local-first zero-configuration product promise.

3. Naive python -m venv copies without relocatable standard library:
   REJECTED. Standard virtual environments embed absolute paths to the host
   toolchain in pyvenv.cfg and rely on system-wide standard library packages.
   When installed on another machine lacking those paths, the interpreter
   fails immediately on missing encodings or core library modules.

4. Standalone redistributable runtime layout (SELECTED):
   On macOS and Linux, we stage a self-contained CPython distribution carrying
   its own binary (runtime/bin/python3) and complete standard library
   (runtime/lib/python3.XX). Path resolution is configured via sitecustomize.py
   and inox_hydra.pth in site-packages, resolving ../lib and ../app relative to
   runtime without requiring PYTHONPATH to be set in the environment. This
   preserves the identical sibling layout across Windows, macOS, and Linux.

IMPORTANT: `app/studio/` deliberately ships without a `data/` directory. Its
absence is what makes `paths.get_app_home()` resolve to the user profile, which
is what allows an update to replace this entire folder without destroying the
user's drafts and leads. Do not add one.

Usage:
    python tools/build_portable.py [--skip-download]

Strict Invariants:
- Zero em-dashes.
- The building interpreter must match the embedded runtime's major and minor
  version, because compiled wheels are ABI specific. fetch_runtime refuses a
  mismatch, and assert_runtime_self_contained checks the staged interpreter.
- No fallback runtime. A runtime that cannot be fetched and verified stops the
  build; it is never assembled from the build machine's own Python.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
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

# macOS and Linux ship python-build-standalone's relocatable CPython, pinned to
# one exact build. The release tag and the Python version together name a file,
# so both are fixed here rather than taken from the runner: the old pair
# (release 20241016 with the runner's patch version) named a file that exists
# only for 3.13.0, and every later patch fell back to copying the build
# machine's interpreter without its standard library.
#
# Bump both together, to a pair the release really contains, and the
# python-version pin in release.yml and desktop.yml with them.
STANDALONE_PYTHON = "3.13.15"
STANDALONE_RELEASE = "20260929"
STANDALONE_BASE_URL = "https://github.com/astral-sh/python-build-standalone/releases/download"

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
#
# ui/ is the React source for the studio interface. The artifact needs the
# BUILT output (studio/frontend_next/, produced by `npm run build`), never the
# source tree, and studio/ui/node_modules is hundreds of megabytes of
# dependencies that would otherwise be copied verbatim into every zip. It is
# gitignored too, and per the same reasoning as backups/ above, that alone does
# not stop this builder: .gitignore governs the index, copy_application walks
# the working tree.
STUDIO_EXCLUDE = {
    "data", "assets", "tests", "__pycache__", ".pytest_cache",
    "backups", "logs", "vault", "ui", "profiles", "exports",
    # A restore stages beside the data, and keeps the originals there if a
    # rollback could not finish. In a source checkout that is inside studio/.
    ".restore-*",
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
    # A Chromium profile's session and password stores. The bridge browser's
    # profile holds the creator's LinkedIn login; paths.py keeps it outside
    # studio/, and this refuses the build if one ever lands in the tree anyway.
    "cookies", "cookies-journal", "login data", "login data-journal",
    "web data", "web data-journal",
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
title Inox Hydra
cd /d "%~dp0"

echo ==========================================================
echo   Inox Hydra - Local Creator Engine
echo   Runs on this computer, on port 8000 when it is free.
echo ==========================================================
echo.

:: The maintainer surface stays off. devtools.is_dev_mode() treats the absence
:: of this variable as off already, so this line is belt and braces: it also
:: clears a value inherited from the shell that launched this one, which is the
:: only way a shipped folder could otherwise come up with the element picker and
:: the annotation ledger visible to a paying creator.
set INOX_DEV_MODE=

:: Everything else is decided by the studio itself (studio\backend\desktop.py):
:: whether the program on port 8000 is really Inox Hydra, a free port when it
:: is not, an engine that is answering before any window opens, and a plain
:: message, with the engine log, when it is not. Batch used to decide this, and
:: treated any program on the port as the studio and a fixed wait as started.
"%~dp0runtime\python.exe" -s -m studio.backend.desktop launch

:: Anything but a clean start on port 8000 leaves this window open, so its
:: message can be read.
if errorlevel 1 (
    echo.
    pause
)
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

UNIX_LAUNCHER = r"""#!/usr/bin/env bash
# ==========================================================
#   Inox Hydra - Local Creator Engine
#   Runs on this computer, on port 8000 when it is free.
# ==========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

unset INOX_DEV_MODE

# The bundled interpreter only. Falling back to a python3 on PATH would run
# the studio on whatever Python this machine has, without its dependencies.
PYTHON_EXE="$SCRIPT_DIR/runtime/bin/python3"
if [ ! -x "$PYTHON_EXE" ]; then
    echo "[!] The bundled Python is missing at $PYTHON_EXE."
    echo "    Extract the whole archive again, keeping the runtime folder."
    exit 1
fi

# Port, readiness, the engine log and the window are decided by the studio
# itself (studio/backend/desktop.py), the same rule on every platform.
exec "$PYTHON_EXE" -s -m studio.backend.desktop launch
"""

UNIX_CLI_LAUNCHER = r"""#!/usr/bin/env bash
# Inox Hydra support toolkit.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_EXE="$SCRIPT_DIR/runtime/bin/python3"
if [ ! -x "$PYTHON_EXE" ]; then
    PYTHON_EXE="$SCRIPT_DIR/runtime/python"
fi
if [ ! -x "$PYTHON_EXE" ]; then
    PYTHON_EXE="python3"
fi

if [ "$#" -eq 0 ]; then
    exec "$PYTHON_EXE" -s -m studio.cli --help
else
    exec "$PYTHON_EXE" -s -m studio.cli "$@"
fi
"""

README = """Inox Hydra (Portable)
=======================================

QUICK START
-----------
1. BEFORE extracting: right click the downloaded ZIP, choose Properties, tick
   "Unblock" near the bottom, then click OK. See the next section for why.
2. Extract the folder anywhere you like. A USB stick is fine.
3. Double click InoxHydra.bat.
4. The launcher starts the studio, waits until it answers, then opens it: in a
   Chrome app window if Google Chrome is installed, otherwise in your default
   browser. If anything stops it, the launcher window stays open and says why.

No Python installation is required. Nothing is sent to any server.


IF WINDOWS BLOCKS IT
--------------------
This is expected, and it is not a sign that anything is wrong.

Windows attaches a "downloaded from the internet" mark to every file inside a
ZIP you download, and this build is not code signed yet. So Windows treats it
with suspicion.

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
  "Port 8000 is in use by another program"
      The launcher checks that the program on port 8000 really is Inox Hydra.
      When it is not, the studio starts on the next free port (8001 to 8009)
      and the launcher says which. The browser extension only connects on port
      8000, so to capture leads and analytics, close the other program, close
      the "Inox Hydra Engine" window, and start InoxHydra.bat again.

  "The studio engine stopped while it was starting"
      The launcher shows the last lines of the engine's log, and the path of
      the whole log (logs\\engine.log in the data folder below). Send that file
      with the report described under "Anything else".

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


BROWSER EXTENSION
-----------------
The extension\\ folder contains the browser bridge that captures leads and
analytics. It is not in a browser store yet. Open the studio's Docs screen and
follow "Install the browser extension that captures leads and analytics": the
studio's Setup screen can open Edge or Brave with it loaded, or you can load
this folder yourself with Developer mode. Keep this folder where it is: the
browser loads the extension from it.


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


UNIX_README = """Inox Hydra (Portable, macOS and Linux preview)
=======================================

This is a preview build. The supported way to run the studio on macOS and
Linux today is from source; see the project README.

QUICK START
-----------
1. Extract the archive anywhere.
2. Run ./InoxHydra.sh from a terminal in the extracted folder.
3. The launcher starts the studio, waits until it answers, and opens it in
   your browser. If anything stops it, it says why and where the log is.

The studio uses port 8000. When another program holds it, the studio starts on
the next free port (8001 to 8009) and the launcher says which. The browser
extension only connects on port 8000.

WHERE YOUR DATA LIVES
---------------------
macOS:  ~/Library/Application Support/InoxHydra
Linux:  $XDG_DATA_HOME/inox-hydra, or ~/.local/share/inox-hydra

Run ./InoxHydra-CLI.sh with no arguments to list the support commands
(backup, restore, export, doctor).
"""


def log(step, message):
    print(f"[{step}] {message}")


def extract_runtime(archive_path, runtime_dir):
    """Extracts a runtime archive (zip or tarball) into runtime_dir."""
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as z:
            z.extractall(runtime_dir)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as t:
            members = t.getmembers()
            has_single_root = all(
                m.name.startswith("python/") or m.name == "python"
                for m in members if m.name
            )
            if has_single_root:
                tmp = tempfile.mkdtemp(prefix="inox_extract_")
                try:
                    t.extractall(tmp)
                    inner = os.path.join(tmp, "python")
                    for item in os.listdir(inner):
                        shutil.move(os.path.join(inner, item), os.path.join(runtime_dir, item))
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            else:
                t.extractall(runtime_dir)
    elif os.path.isdir(archive_path):
        shutil.copytree(archive_path, runtime_dir, dirs_exist_ok=True)
    else:
        raise ValueError(f"Unrecognized runtime archive format: {archive_path}")


def get_runtime_interpreter(runtime_dir):
    """
    Returns the path to the executable Python interpreter in the runtime directory.
    Checks python.exe on Windows, bin/python3, bin/python, or python3 on Unix.
    """
    if platform.system() == "Windows":
        return os.path.join(runtime_dir, "python.exe")
    for cand in (
        os.path.join(runtime_dir, "bin", "python3"),
        os.path.join(runtime_dir, "bin", "python"),
        os.path.join(runtime_dir, "python3"),
    ):
        if os.path.exists(cand):
            return cand
    return os.path.join(runtime_dir, "bin", "python3")


def standalone_runtime_name(system, machine):
    """The python-build-standalone archive for this platform, at the pinned build."""
    arch = "aarch64" if machine.lower() in ("arm64", "aarch64") else "x86_64"
    target = "apple-darwin" if system == "Darwin" else "unknown-linux-gnu"
    return f"cpython-{STANDALONE_PYTHON}+{STANDALONE_RELEASE}-{arch}-{target}-install_only.tar.gz"


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_verified(url, sums_url, name, target):
    """
    Downloads one archive and checks it against its release's SHA256SUMS.

    Anything short of a verified file stops the build and leaves nothing in the
    cache, so a truncated or substituted download cannot be picked up by the
    next build as "using cached".
    """
    partial = target + ".partial"
    sums = target + ".SHA256SUMS"
    try:
        log("runtime", f"downloading {url}")
        urllib.request.urlretrieve(url, partial)
        urllib.request.urlretrieve(sums_url, sums)
        with open(sums, encoding="utf-8") as handle:
            published = {
                parts[1].lstrip("*"): parts[0].lower()
                for parts in (line.split() for line in handle) if len(parts) == 2
            }
        expected = published.get(name)
        if not expected:
            raise SystemExit(f"REFUSING TO BUILD. {name} is not listed in {sums_url}")
        actual = _sha256(partial)
        if actual != expected:
            raise SystemExit(
                f"REFUSING TO BUILD. {name} does not match its published checksum "
                f"(expected {expected}, downloaded {actual})."
            )
        os.replace(partial, target)
        log("runtime", f"downloaded and verified {os.path.getsize(target):,} bytes, sha256 {actual}")
        return target
    except SystemExit:
        raise
    except Exception as err:
        raise SystemExit(
            f"REFUSING TO BUILD. The runtime could not be downloaded ({err}). "
            f"Nothing falls back to the build machine's Python. URL: {url}"
        )
    finally:
        for leftover in (partial, sums):
            if os.path.exists(leftover):
                os.remove(leftover)


def fetch_runtime(skip_download=False):
    """
    Downloads an embeddable or standalone CPython distribution, caching it
    between builds in build_artifacts/runtime_cache.

    On Windows: python-{version}-embed-amd64.zip from python.org, at the
    building interpreter's own version.
    On macOS and Linux: the pinned python-build-standalone build, verified
    against its release's SHA256SUMS.

    There is no fallback. When the runtime cannot be fetched, or
    --skip-download is passed without a cached copy, the build stops. It used
    to assemble a "runtime" from the building interpreter, which in a virtual
    environment meant a binary with no standard library that only ran on the
    machine that built it.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    system = platform.system()

    if system == "Windows":
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

    # Compiled wheels are vendored by the building interpreter, so it and the
    # runtime have to agree on major and minor, or nothing in lib/ imports.
    builder = f"{sys.version_info.major}.{sys.version_info.minor}"
    pinned = ".".join(STANDALONE_PYTHON.split(".")[:2])
    if builder != pinned:
        raise SystemExit(
            f"REFUSING TO BUILD. The build interpreter is Python {builder} and the bundled "
            f"runtime is {STANDALONE_PYTHON}. Compiled wheels are ABI specific: build with "
            f"Python {pinned}, or move STANDALONE_PYTHON and STANDALONE_RELEASE together."
        )

    name = standalone_runtime_name(system, platform.machine())
    cached = os.path.join(CACHE_DIR, name)
    if os.path.exists(cached) and os.path.getsize(cached) > 0:
        log("runtime", f"using cached {name}")
        return cached

    if skip_download:
        raise SystemExit(
            f"--skip-download was passed but no cached runtime exists at {cached}. "
            "Nothing falls back to the build machine's Python."
        )

    base = f"{STANDALONE_BASE_URL}/{STANDALONE_RELEASE}"
    return _download_verified(f"{base}/{name.replace('+', '%2B')}", f"{base}/SHA256SUMS", name, cached)


# Run by the staged interpreter, from an unrelated folder, with nothing in the
# environment that could point it back at the build machine's Python.
_RUNTIME_PROBE = r"""
import json, sys, encodings, sqlite3, ssl
print(json.dumps({
    "version": "%d.%d.%d" % sys.version_info[:3],
    "base_prefix": sys.base_prefix,
    "stdlib": encodings.__file__,
}))
"""


def assert_runtime_self_contained(runtime_dir):
    """
    Refuses a runtime that only runs because the build machine has Python.

    Runs the staged interpreter with a scrubbed environment from a temporary
    folder and checks where it found its standard library. Copying a binary
    out of a virtual environment produces one that reports a prefix under the
    host's /usr; that is the case this exists for. Returns what was measured.
    """
    interpreter = get_runtime_interpreter(runtime_dir)
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("PYTHON") and k.upper() not in {"VIRTUAL_ENV", "CONDA_PREFIX"}}
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        env["PATH"] = os.pathsep.join([os.path.join(system_root, "System32"), system_root])
    else:
        env["PATH"] = "/usr/bin:/bin"
    elsewhere = tempfile.mkdtemp(prefix="inox_runtime_probe_")
    try:
        result = subprocess.run([interpreter, "-s", "-c", _RUNTIME_PROBE], cwd=elsewhere, env=env,
                                capture_output=True, text=True, timeout=120)
    except OSError as err:
        raise SystemExit(f"REFUSING TO BUILD. The staged interpreter does not run: {err}")
    finally:
        shutil.rmtree(elsewhere, ignore_errors=True)
    if result.returncode != 0:
        raise SystemExit("REFUSING TO BUILD. The staged interpreter does not start on its own:\n"
                         + (result.stderr or result.stdout)[-2000:])

    report = json.loads(result.stdout.strip().splitlines()[-1])
    root = os.path.normcase(os.path.realpath(runtime_dir))
    borrowed = [label for label, path in (("prefix", report["base_prefix"]), ("standard library", report["stdlib"]))
                if not os.path.normcase(os.path.realpath(path)).startswith(root)]
    if borrowed:
        raise SystemExit(
            "REFUSING TO BUILD. The runtime is not self-contained: its "
            + " and ".join(borrowed) + f" come from outside {runtime_dir} "
            f"(prefix {report['base_prefix']}, standard library {report['stdlib']}). "
            "It would run only on a machine that already has this Python."
        )
    builder = f"{sys.version_info.major}.{sys.version_info.minor}"
    if not report["version"].startswith(builder + "."):
        raise SystemExit(f"REFUSING TO BUILD. The runtime is Python {report['version']} and the "
                         f"vendored wheels are for {builder}.")
    log("runtime", f"self-contained Python {report['version']}, standard library inside runtime/")
    return report


def write_path_file(runtime_dir):
    """
    Rewrites python3XX._pth (Windows) or configures sitecustomize and .pth (Unix)
    so the embedded interpreter resolves lib/ and app/ relative to runtime.

    Paths are resolved relative to the directory holding the runtime. On Windows,
    python3XX._pth with import site is required. On macOS and Linux, an
    inox_hydra.pth file in site-packages and sitecustomize.py ensure that
    ../lib and ../app are on sys.path without relying on environment variables.
    """
    if platform.system() == "Windows":
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
    else:
        py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        target_sp = os.path.join(runtime_dir, "lib", py_ver, "site-packages")
        os.makedirs(target_sp, exist_ok=True)

        pth_path = os.path.join(target_sp, "inox_hydra.pth")
        with open(pth_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("../../../../lib\n../../../../app\n")

        sc_path = os.path.join(target_sp, "sitecustomize.py")
        sc_content = "\n".join([
            "import os",
            "import sys",
            "",
            "_cur = os.path.dirname(os.path.abspath(__file__))",
            "_runtime = None",
            "for _ in range(6):",
            "    if os.path.basename(_cur) == 'runtime':",
            "        _runtime = _cur",
            "        break",
            "    _parent = os.path.dirname(_cur)",
            "    if _parent == _cur:",
            "        break",
            "    _cur = _parent",
            "",
            "if _runtime:",
            "    _payload = os.path.dirname(_runtime)",
            "    _lib = os.path.join(_payload, 'lib')",
            "    _app = os.path.join(_payload, 'app')",
            "    if os.path.isdir(_lib) and _lib not in sys.path:",
            "        sys.path.insert(0, _lib)",
            "    if os.path.isdir(_app) and _app not in sys.path:",
            "        sys.path.insert(0, _app)",
            "",
        ])
        with open(sc_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sc_content)

        # No pyvenv.cfg. A standalone runtime finds its own library next to its
        # binary. The "home = ." this wrote was read relative to the working
        # directory, so where the launcher was started from decided where the
        # interpreter looked ("Could not find platform dependent libraries").
        # The user site that it also switched off is kept out by -s on every
        # command line that starts this interpreter.
        log("runtime", f"configured Unix runtime paths in {os.path.relpath(target_sp, runtime_dir)}")


def vendor_dependencies(lib_dir):
    """
    Installs runtime dependencies into lib/ as a flat directory.

    Uses the building interpreter, so the compiled wheels match the embedded
    runtime's ABI. fetch_runtime refuses a runtime of another major or minor
    version, and assert_runtime_self_contained checks the staged one.
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


def assert_help_shipped(studio_dir):
    """
    Refuses an artifact whose Docs screen would show its help sections empty.

    The help articles were never staged, and nothing checked, so every portable
    copy shipped with 0 documents in each help section.
    """
    sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
    import prepare_package

    absent = prepare_package.missing_help(os.path.join(studio_dir, "docs"))
    if absent:
        raise SystemExit(
            f"REFUSING TO BUILD. {len(absent)} help document(s) are missing from the artifact's docs: "
            + ", ".join(absent[:5])
            + ". Run tools/prepare_package.py, which stages them into studio/docs."
        )


def assert_interface_built(studio_dir):
    """
    Refuses an artifact whose window would open on a 503 instead of the studio.

    studio/frontend_next is gitignored, and the server has no fallback page, so
    a checkout that skipped `npm run build` copies cleanly and ships a product
    that answers "The studio interface has not been built". The desktop
    workflow did exactly that for every installer. Both channels copy the
    application through copy_application, so the check sits here once.
    """
    index = os.path.join(studio_dir, "frontend_next", "index.html")
    if not os.path.isfile(index):
        raise SystemExit(
            "REFUSING TO BUILD. The studio interface is missing from the artifact "
            f"({os.path.relpath(index, os.path.dirname(studio_dir))}). Run "
            "`npm --prefix studio/ui ci` and `npm --prefix studio/ui run build` first."
        )


def copy_application(app_dir):
    """Copies the studio package, excluding user state, tests, caches and secrets."""
    assert_interface_built(os.path.join(REPO_ROOT, "studio"))
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
    assert_help_shipped(target)
    assert_interface_built(target)
    log("app", f"copied studio package, {sum(len(f) for _, _, f in os.walk(target))} files")
    return target


def main():
    skip_download = "--skip-download" in sys.argv

    if platform.system() == "Windows":
        platform_tag = "win64"
    elif platform.system() == "Darwin":
        # One architecture per build: the runtime is the runner's, not universal.
        platform_tag = f"macos-{platform.machine()}"
    else:
        platform_tag = f"linux-{platform.machine()}"

    log("prep", f"staging bundled content for {platform_tag}")
    if subprocess.run([sys.executable, os.path.join(REPO_ROOT, "tools", "prepare_package.py")],
                      cwd=REPO_ROOT).returncode != 0:
        raise SystemExit("prepare_package failed")

    sys.path.insert(0, REPO_ROOT)
    from studio.__version__ import __version__

    name = f"InoxHydra-{__version__}-{platform_tag}"
    staging = os.path.join(BUILD_ROOT, name)
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    log("prep", f"building {name}")

    runtime_zip = fetch_runtime(skip_download)
    runtime_dir = os.path.join(staging, "runtime")
    os.makedirs(runtime_dir)
    extract_runtime(runtime_zip, runtime_dir)

    if platform.system() == "Windows":
        embedded = os.path.join(runtime_dir, "python.exe")
        assert os.path.exists(embedded), "embeddable runtime is missing python.exe"
    else:
        embedded = get_runtime_interpreter(runtime_dir)
        assert os.path.exists(embedded), f"runtime is missing python interpreter at {embedded}"
        try:
            os.chmod(embedded, 0o755)
        except OSError:
            pass
    write_path_file(runtime_dir)
    assert_runtime_self_contained(runtime_dir)

    lib_dir = os.path.join(staging, "lib")
    os.makedirs(lib_dir)
    vendor_dependencies(lib_dir)

    app_dir = os.path.join(staging, "app")
    os.makedirs(app_dir)
    copy_application(app_dir)

    shutil.copytree(os.path.join(REPO_ROOT, "studio", "extension"),
                    os.path.join(staging, "extension"),
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc",
                        *SECRET_PATTERNS, *ALWAYS_SECRET))
    log("app", "copied unpacked extension for store submission and fallback")

    # Windows batch launchers
    with open(os.path.join(staging, "InoxHydra.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(LAUNCHER)
    with open(os.path.join(staging, "InoxHydra-CLI.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(CLI_LAUNCHER)

    # Unix shell launchers for Linux / macOS
    sh_launcher = os.path.join(staging, "InoxHydra.sh")
    with open(sh_launcher, "w", encoding="utf-8", newline="\n") as f:
        f.write(UNIX_LAUNCHER)
    os.chmod(sh_launcher, 0o755)

    sh_cli = os.path.join(staging, "InoxHydra-CLI.sh")
    with open(sh_cli, "w", encoding="utf-8", newline="\n") as f:
        f.write(UNIX_CLI_LAUNCHER)
    os.chmod(sh_cli, 0o755)

    if os.path.exists(os.path.join(REPO_ROOT, "create_desktop_shortcut.sh")):
        sh_shortcut = os.path.join(staging, "create_desktop_shortcut.sh")
        shutil.copy2(os.path.join(REPO_ROOT, "create_desktop_shortcut.sh"), sh_shortcut)
        os.chmod(sh_shortcut, 0o755)

    with open(os.path.join(staging, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(README if platform.system() == "Windows" else UNIX_README)

    shutil.copy2(os.path.join(REPO_ROOT, "create_desktop_shortcut.vbs"), staging)
    shutil.copy2(os.path.join(REPO_ROOT, "LICENSE"), staging)

    # Application icons
    icon_source = os.path.join(REPO_ROOT, "assets", "inox_hydra.ico")
    assert os.path.isfile(icon_source), (
        "assets/inox_hydra.ico is missing. Run tools/generate_icons.py before building, "
        "or the shipped artifact falls back to the generic Windows application icon."
    )
    os.makedirs(os.path.join(staging, "assets"), exist_ok=True)
    shutil.copy2(icon_source, os.path.join(staging, "assets", "inox_hydra.ico"))
    png_icon = os.path.join(REPO_ROOT, "assets", "inox_hydra.png")
    if os.path.isfile(png_icon):
        shutil.copy2(png_icon, os.path.join(staging, "assets", "inox_hydra.png"))
    log("app", "copied application icons")

    assert_no_secrets(staging)

    log("zip", "compressing zip package")
    archive = os.path.join(BUILD_ROOT, name + ".zip")
    if os.path.exists(archive):
        os.remove(archive)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, filenames in os.walk(staging):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                zinfo = zipfile.ZipInfo(os.path.join(name, os.path.relpath(full, staging)))
                zinfo.date_time = (2026, 1, 1, 0, 0, 0)
                if os.access(full, os.X_OK):
                    zinfo.external_attr = 0o755 << 16
                else:
                    zinfo.external_attr = 0o644 << 16
                with open(full, "rb") as fp:
                    z.writestr(zinfo, fp.read(), compress_type=zipfile.ZIP_DEFLATED)

    if platform.system() != "Windows":
        log("tar", "compressing tarball package")
        tar_archive = os.path.join(BUILD_ROOT, name + ".tar.gz")
        if os.path.exists(tar_archive):
            os.remove(tar_archive)
        with tarfile.open(tar_archive, "w:gz") as tar:
            tar.add(staging, arcname=name)
        log("done", f"tarball created: {tar_archive}")

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
