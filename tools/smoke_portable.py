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
SMOKE = r'''
import os, sys, tempfile
os.environ["INOX_HYDRA_HOME"] = tempfile.mkdtemp(prefix="inox_smoke_")

failures = []
def check(label, cond, detail=""):
    print(f"  {label:38s} {'PASS' if cond else 'FAIL'} {detail}")
    if not cond:
        failures.append(label)

# The interpreter must be the embedded one, not a host installation.
check("runs from the embedded runtime",
      os.path.normcase("runtime") in os.path.normcase(sys.prefix),
      sys.version.split()[0])

import sqlite3, ssl, ctypes
check("sqlite3 present", sqlite3.sqlite_version_info >= (3, 30), sqlite3.sqlite_version)
check("ssl present", bool(ssl.OPENSSL_VERSION))
check("ctypes present (DPAPI vault)", hasattr(ctypes, "windll"))

import fastapi, uvicorn, pydantic, PIL, apscheduler, requests, httpx, multipart, pymupdf
check("vendored dependencies import", True,
      f"fastapi {fastapi.__version__}, pymupdf {pymupdf.__doc__ and 'ok'}")

from fastapi.testclient import TestClient
import studio.backend.app as m
import studio.backend.paths as p
import studio.backend.migrations as mig

check("application imports", bool(m.app.routes), f"{len(m.app.routes)} routes")

with TestClient(m.app) as c:
    r = c.get("/")
    check("serves the studio UI", r.status_code == 200 and "<html" in r.text.lower(),
          f"{len(r.text)} bytes")
    r = c.get("/api/docs")
    mods = r.json().get("modules", []) if r.status_code == 200 else []
    check("serves documentation", len(mods) > 0, f"{len(mods)} modules")
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


def scrubbed_environment():
    """
    Environment for the child process, with every route back to a host Python
    removed. PATH is reduced to the Windows system directories, because a
    stranger's machine is not guaranteed to have anything else.
    """
    env = {
        k: v for k, v in os.environ.items()
        if not k.upper().startswith("PYTHON") and k.upper() not in {"VIRTUAL_ENV", "CONDA_PREFIX"}
    }
    system_root = env.get("SystemRoot", r"C:\Windows")
    env["PATH"] = os.pathsep.join([
        os.path.join(system_root, "System32"),
        system_root,
        os.path.join(system_root, "System32", "Wbem"),
    ])
    return env


def main() -> int:
    artifact = find_artifact()
    print(f"artifact: {os.path.basename(artifact)} "
          f"({os.path.getsize(artifact) / 1024 / 1024:.1f} MB)")

    workdir = tempfile.mkdtemp(prefix="inox_smoke_extract_")
    try:
        with zipfile.ZipFile(artifact) as z:
            z.extractall(workdir)

        roots = [d for d in glob.glob(os.path.join(workdir, "*")) if os.path.isdir(d)]
        if len(roots) != 1:
            raise SystemExit(f"expected a single top level folder in the ZIP, found {roots}")
        root = roots[0]

        interpreter = os.path.join(root, "runtime", "python.exe")
        if not os.path.exists(interpreter):
            raise SystemExit(f"no embedded interpreter at {interpreter}")

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
            [interpreter, script],
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
