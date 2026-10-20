"""
Portable Artifact Smoke Test: Prove It Runs With No Python Installed.
=====================================================================
Extracts the built ZIP to a scratch directory and drives it using ONLY the
interpreter embedded inside it, with the environment scrubbed of anything that
could let the host's Python leak in.

This is the gate that separates "we produced a ZIP" from "a stranger can run
it". The failure it guards against is a build that works perfectly on the
machine that made it because a system Python quietly supplied a missing piece.

Usage:
    python tools/build_portable.py && python tools/smoke_portable.py
    python tools/stage_desktop_payload.py && python tools/smoke_portable.py --payload desktop/payload

Exits non-zero on any failure, so it can gate a release.

Strict Invariants:
- Zero em-dashes.
- The host interpreter must never appear on the child's path.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARTIFACT_GLOB = os.path.join(REPO_ROOT, "dist", "portable", "*.zip")

# Runs inside the artifact, executed by the artifact's own interpreter.
#
# INOX_SMOKE_SOURCE_TREE=1 runs the same body against a source checkout, which
# is how tests/test_qc2_r1_smoke.py keeps it honest on every commit: only the
# check that the interpreter is the embedded one is skipped there.
SMOKE = r'''
import os, sys, tempfile
os.environ["INOX_HYDRA_HOME"] = tempfile.mkdtemp(prefix="inox_smoke_")
SOURCE_TREE = os.environ.get("INOX_SMOKE_SOURCE_TREE") == "1"

failures = []
def check(label, cond, detail=""):
    print(f"  {label:38s} {'PASS' if cond else 'FAIL'} {detail}")
    if not cond:
        failures.append(label)

# The interpreter must be the embedded one, not a host installation. Both the
# prefix and the standard library are checked: a runtime that only borrows the
# build machine's library looks embedded by its prefix alone.
import encodings
if not SOURCE_TREE:
    runtime = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(sys.executable))))
    if os.path.basename(runtime) == "bin":
        runtime = os.path.dirname(runtime)
    check("runs from the embedded runtime",
          os.path.basename(runtime) == "runtime"
          and os.path.normcase(os.path.realpath(sys.base_prefix)).startswith(runtime),
          sys.version.split()[0])
    check("standard library is the runtime's own",
          os.path.normcase(os.path.realpath(encodings.__file__)).startswith(runtime),
          encodings.__file__)

import sqlite3, ssl, ctypes
check("sqlite3 present", sqlite3.sqlite_version_info >= (3, 30), sqlite3.sqlite_version)
check("ssl present", bool(ssl.OPENSSL_VERSION))
if os.name == "nt":
    check("ctypes present (DPAPI vault)", hasattr(ctypes, "windll"))

import fastapi, uvicorn, pydantic, PIL, apscheduler, requests, httpx, multipart, pymupdf
check("vendored dependencies import", True,
      f"fastapi {fastapi.__version__}, pymupdf {pymupdf.__doc__ and 'ok'}")

from fastapi.testclient import TestClient
import studio.backend.app as m
import studio.backend.paths as p
import studio.backend.migrations as mig
import studio.backend.security as sec

check("application imports", bool(m.app.routes), f"{len(m.app.routes)} routes")

# Pointed at the loopback origin and carrying the installation's token, as
# verify_package.py does and as every real caller does. The API checks Host,
# Origin and token on every request, so a bare TestClient (Host "testserver",
# no credential) is refused with 403 before it reaches a route, and this gate
# failed every check for every release.
with TestClient(
    m.app,
    base_url="http://127.0.0.1:8000",
    headers={sec.TOKEN_HEADER: sec.get_or_create_token()},
) as c:
    r = c.get("/api/v1/health")
    check("health names this application", r.status_code == 200 and r.json().get("app") == "inox-hydra")
    r = c.get("/")
    check("serves the studio UI", r.status_code == 200 and "<html" in r.text.lower(),
          f"{len(r.text)} bytes")
    r = c.get("/api/docs")
    docs = r.json() if r.status_code == 200 else {}
    help_count = sum(s["count"] for s in docs.get("sections", []) if s.get("kind") == "help")
    check("serves the help", help_count > 0, f"{help_count} help documents")
    if not SOURCE_TREE:
        # A packaged copy carries the help and nothing written for maintainers.
        shipped = [e["path"] for e in docs.get("library", [])]
        internal = [path for path in shipped
                    if not path.startswith("help/") and path != "strategy_playbook.md"]
        check("ships no maintainer or retired documents", not internal, ", ".join(internal[:3]))
    for ep in ("/api/analytics/kpis", "/api/posts", "/api/leads", "/api/v1/schema/status"):
        check(f"GET {ep}", c.get(ep).status_code == 200)

d = p.describe()
check("state resolves outside the artifact", not os.path.normcase(d["app_home"]).startswith(
      os.path.normcase(os.path.dirname(sys.prefix))), d["app_home"])
check("database created on first launch", d["db_exists"], f"{d['db_size_bytes']:,} bytes")

s = mig.describe()
check("schema ledger current", s["up_to_date"], f"v{s['current_version']}")

print()
if failures:
    print("SMOKE FAILED: " + ", ".join(failures))
    sys.exit(1)
print("SMOKE PASSED")
'''


def find_artifact():
    matches = sorted(glob.glob(ARTIFACT_GLOB))
    if not matches:
        raise SystemExit(
            f"no portable artifact found at {ARTIFACT_GLOB}. "
            "Run: python tools/build_portable.py"
        )
    return matches[-1]


def find_interpreter(root):
    """The embedded interpreter: runtime\\python.exe on Windows, runtime/bin/python3 elsewhere."""
    for candidate in (
        os.path.join(root, "runtime", "python.exe"),
        os.path.join(root, "runtime", "bin", "python3"),
    ):
        if os.path.isfile(candidate):
            return candidate
    raise SystemExit(f"no embedded interpreter under {os.path.join(root, 'runtime')}")


def scrubbed_environment():
    """
    Environment for the child process, with every route back to a host Python
    removed. PATH is reduced to the system directories, because a stranger's
    machine is not guaranteed to have anything else.
    """
    env = {
        k: v for k, v in os.environ.items()
        if not k.upper().startswith(("PYTHON", "INOX_"))
        and k.upper() not in {"VIRTUAL_ENV", "CONDA_PREFIX"}
    }
    if os.name == "nt":
        system_root = env.get("SystemRoot", r"C:\Windows")
        env["PATH"] = os.pathsep.join([
            os.path.join(system_root, "System32"),
            system_root,
            os.path.join(system_root, "System32", "Wbem"),
        ])
    else:
        env["PATH"] = "/usr/bin:/bin"
    return env


def stage(workdir, payload=None):
    """
    The tree to drive, in a fresh folder the build never wrote to.

    A ZIP is extracted. A payload directory (the desktop app's desktop/payload)
    is copied, so its interpreter runs from a path it was not built at, which
    is what an installed copy does.
    """
    if payload:
        root = os.path.join(workdir, "payload")
        shutil.copytree(payload, root, symlinks=True)
        return root

    artifact = find_artifact()
    print(f"artifact: {os.path.basename(artifact)} "
          f"({os.path.getsize(artifact) / 1024 / 1024:.1f} MB)")
    with zipfile.ZipFile(artifact) as z:
        for info in z.infolist():
            z.extract(info, workdir)
            # extract() drops the permission bits, and a Unix interpreter needs its own.
            mode = (info.external_attr >> 16) & 0o777
            if mode and os.name != "nt":
                os.chmod(os.path.join(workdir, info.filename), mode)

    roots = [d for d in glob.glob(os.path.join(workdir, "*")) if os.path.isdir(d)]
    if len(roots) != 1:
        raise SystemExit(f"expected a single top level folder in the ZIP, found {roots}")
    return roots[0]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    payload = None
    if "--payload" in argv:
        payload = os.path.abspath(argv[argv.index("--payload") + 1])

    workdir = tempfile.mkdtemp(prefix="inox_smoke_extract_")
    try:
        root = stage(workdir, payload)
        interpreter = find_interpreter(root)

        # Absence of this directory is what routes user state to the profile.
        data_dir = os.path.join(root, "app", "studio", "data")
        if os.path.exists(data_dir):
            raise SystemExit(
                "the artifact contains app/studio/data, which would make it write user "
                "state inside the install folder. An update would then destroy that data."
            )

        print(f"extracted to: {root}")
        print("driving it with the embedded interpreter and a scrubbed environment")
        print()

        script = os.path.join(workdir, "_smoke.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(SMOKE)

        result = subprocess.run(
            # -s: no user site packages, as every launcher starts it.
            [interpreter, "-s", script],
            cwd=root, env=scrubbed_environment(),
            capture_output=True, text=True, timeout=900,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr[-4000:])
        return result.returncode
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
