"""
Release Verification: Build A Wheel And Prove It Actually Works.
================================================================
Builds the distributable, installs it into a genuinely clean virtual
environment (no system site packages), and boots it from an unrelated working
directory to confirm it serves its own interface.

This exists because `python -m build` reporting success proves almost nothing.
The first wheel built from this tree installed cleanly and could not serve a
single page, because no data files were declared. Two dependencies the running
application requires (apscheduler, python-multipart) were also absent from the
metadata and only surfaced here.

Usage:
    python tools/verify_package.py

Exits non-zero on any failure, so it can gate a release in CI.

Strict Invariants:
- Zero em-dashes.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

GATE_SCRIPT = '''
import os, sys, tempfile
os.environ["INOX_HYDRA_HOME"] = tempfile.mkdtemp(prefix="inox_verify_")

from fastapi.testclient import TestClient
import studio.backend.app as m
import studio.backend.paths as p

install_root = os.path.dirname(os.path.dirname(m.__file__))
failures = []

def check(label, condition, detail=""):
    print(f"  {label:34s} {'PASS' if condition else 'FAIL'} {detail}")
    if not condition:
        failures.append(label)

# Context manager so lifespan startup runs, exactly as on a real first launch.
with TestClient(m.app) as c:
    r = c.get("/")
    check("serves the single page app", r.status_code == 200 and "<html" in r.text.lower(),
          f"({len(r.text)} bytes)")

    r = c.get("/api/docs")
    mods = r.json().get("modules", []) if r.status_code == 200 else []
    check("lists documentation modules", len(mods) > 0, f"({len(mods)} modules)")

    for mod in mods:
        rr = c.get("/api/docs/" + str(mod["id"]))
        body = rr.json().get("content", "") if rr.status_code == 200 else ""
        check(f"serves doc {mod['id']}", len(body) > 500, f"({len(body)} bytes)")

    for ep in ("/api/analytics/kpis", "/api/posts", "/api/leads", "/api/queue/smart-slots"):
        rr = c.get(ep)
        check(f"GET {ep}", rr.status_code == 200)

d = p.describe()
check("database created on first run", d["db_exists"], f"({d['db_size_bytes']:,} bytes)")
check("state lives outside install dir", not d["app_home"].startswith(install_root), d["app_home"])
check("docs resolve from the package", d["docs_source"] == "packaged")

print()
if failures:
    print("VERIFY FAILED: " + ", ".join(failures))
    sys.exit(1)
print("VERIFY PASSED")
'''


def run(cmd, **kw):
    result = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if result.returncode != 0:
        print(result.stdout[-4000:])
        print(result.stderr[-4000:])
    return result


def main() -> int:
    print("1. Staging bundled content")
    if run([sys.executable, os.path.join(REPO_ROOT, "tools", "prepare_package.py")],
           cwd=REPO_ROOT).returncode != 0:
        return 1

    # --no-isolation below means the build backend is taken from THIS
    # environment. setuptools stopped being preinstalled with Python 3.12, so
    # check for it here rather than letting `build` emit a traceback that buries
    # the actual cause.
    if importlib.util.find_spec("setuptools") is None:
        print("   setuptools is not installed, and the build runs with --no-isolation.")
        print("   Fix: pip install setuptools")
        return 1

    print("2. Building wheel")
    for junk in ("dist", "build"):
        shutil.rmtree(os.path.join(REPO_ROOT, junk), ignore_errors=True)
    if run([sys.executable, "-m", "build", "--wheel", "--no-isolation"], cwd=REPO_ROOT).returncode != 0:
        print("   build failed")
        return 1

    dist_dir = os.path.join(REPO_ROOT, "dist")
    wheels = [f for f in os.listdir(dist_dir) if f.endswith(".whl")]
    if len(wheels) != 1:
        print(f"   expected exactly one wheel, found {wheels}")
        return 1
    wheel = os.path.join(dist_dir, wheels[0])
    print(f"   built {wheels[0]}")

    print("3. Creating clean virtual environment")
    venv_dir = tempfile.mkdtemp(prefix="inox_verify_venv_")
    if run([sys.executable, "-m", "venv", venv_dir]).returncode != 0:
        return 1
    py = os.path.join(venv_dir, "Scripts" if sys.platform == "win32" else "bin",
                      "python.exe" if sys.platform == "win32" else "python")

    print("4. Installing the wheel and its declared dependencies")
    if run([py, "-m", "pip", "install", "--quiet", wheel]).returncode != 0:
        print("   install failed. A dependency is probably undeclared.")
        return 1

    print("5. Booting from an unrelated working directory")
    result = subprocess.run([py, "-c", GATE_SCRIPT], cwd=tempfile.gettempdir(),
                            capture_output=True, text=True, timeout=600)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr[-4000:])

    shutil.rmtree(venv_dir, ignore_errors=True)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
