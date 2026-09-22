"""
Desktop Payload Staging: The Runtime The Tauri Bundle Carries.
==============================================================

The native shell has no Python of its own. It starts the same embeddable
interpreter the portable ZIP ships, which means the two artifacts must carry
byte identical payloads or they are two products that behave differently and
only one of them gets tested.

So this does not build a payload. It calls the functions in build_portable that
already do, and lays the result out where tauri.conf.json expects to find it:

    desktop/payload/runtime/    embeddable CPython, with its path file rewritten
    desktop/payload/lib/        vendored third party dependencies
    desktop/payload/app/studio/ the application package

Why PyInstaller is still not involved, even though the Tauri sidecar
documentation assumes it: the reasoning in build_portable has not changed. An
unsigned PyInstaller bootloader trips antivirus heuristics, and there is no
support channel to walk a stranger through a quarantine. A folder of ordinary
files inside a signed installer does not have that problem, and the outer
executable is the Rust binary, which signs cleanly.

Usage:
    python tools/stage_desktop_payload.py [--skip-download]

Strict Invariants:
- Zero em-dashes.
- Never diverge from the portable layout. runtime/python3XX._pth resolves
  ..\\lib and ..\\app relative to itself, and the Rust shell relies on it.
"""

import os
import shutil
import subprocess
import sys
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PAYLOAD_ROOT = os.path.join(REPO_ROOT, "desktop", "payload")

sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
sys.path.insert(0, REPO_ROOT)

import build_portable  # noqa: E402  the path insert above is the point


def main():
    skip_download = "--skip-download" in sys.argv

    build_portable.log("prep", "staging bundled content and propagating version")
    if subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "prepare_package.py")],
        cwd=REPO_ROOT,
    ).returncode != 0:
        raise SystemExit("prepare_package failed")

    if os.path.exists(PAYLOAD_ROOT):
        shutil.rmtree(PAYLOAD_ROOT)
    os.makedirs(PAYLOAD_ROOT)

    runtime_zip = build_portable.fetch_runtime(skip_download)
    runtime_dir = os.path.join(PAYLOAD_ROOT, "runtime")
    os.makedirs(runtime_dir)
    with zipfile.ZipFile(runtime_zip) as archive:
        archive.extractall(runtime_dir)

    interpreter = os.path.join(runtime_dir, "python.exe")
    assert os.path.exists(interpreter), "embeddable runtime is missing python.exe"

    # This is what lets the Rust shell spawn the interpreter without setting
    # PYTHONPATH. Losing it means an engine that cannot import its own package.
    build_portable.write_path_file(runtime_dir)

    lib_dir = os.path.join(PAYLOAD_ROOT, "lib")
    os.makedirs(lib_dir)
    build_portable.vendor_dependencies(lib_dir)

    app_dir = os.path.join(PAYLOAD_ROOT, "app")
    os.makedirs(app_dir)
    build_portable.copy_application(app_dir)

    # The same guarantee the portable build asserts. Its absence is what makes
    # paths.get_app_home() resolve to the user profile, which is what allows an
    # update to replace the installed folder without destroying drafts.
    assert not os.path.exists(os.path.join(app_dir, "studio", "data")), (
        "payload/app/studio/data exists. The installer would then write user "
        "state inside Program Files, and an update would destroy it."
    )

    # Across the whole payload, not only the application package. The runtime
    # and lib directories are third party content, but this is the last point
    # at which anything can be caught before it is sealed into an installer.
    build_portable.assert_no_secrets(PAYLOAD_ROOT)

    total = sum(len(files) for _, _, files in os.walk(PAYLOAD_ROOT))
    build_portable.log("payload", f"staged {total} files into desktop/payload")


if __name__ == "__main__":
    main()
