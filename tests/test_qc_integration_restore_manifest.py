"""
A backup whose manifest is not an object is refused in words, not a traceback.
==============================================================================
Found while verifying PLATFORM-17: the backups list now marks such a file
unreadable, but `studio.cli restore` on it printed "'list' object has no
attribute 'get'".
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_a_malformed_manifest_is_refused_in_words():
    home = tempfile.mkdtemp(prefix="inox_qc_manifest_")
    archive = os.path.join(home, "broken_backup.zip")
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("backup_manifest.json", json.dumps(["not", "an", "object"]))
        handle.writestr("linkedin_studio.db", b"")
    env = dict(os.environ, INOX_HYDRA_HOME=home)
    run = subprocess.run([sys.executable, "-m", "studio.cli", "restore", archive, "--yes"],
                         cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    output = run.stdout + run.stderr
    assert run.returncode != 0
    assert "Traceback" not in output and "has no attribute" not in output, output
    assert "Not restored" in output, output
