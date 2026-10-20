"""
The macOS and Linux runtime is self-contained, or the build fails. [INS-03]

The standalone runtime URL paired release 20241016 with whatever patch version
the runner had. That release holds only 3.13.0, so every later patch 404ed and
the builder fell back, silently, to copying the build machine's interpreter.
In a virtual environment that copy holds the binary and site-packages and no
standard library: measured, it ran only because the host had Python 3.12 at
/usr/lib. Nothing ran the staged interpreter from anywhere else, so it would
have shipped.

Now the runtime is one pinned build, checked against its release's SHA256SUMS,
there is no fallback, and the staged interpreter is run with a scrubbed
environment to prove its standard library is its own.

Strict Invariants:
- Zero em-dashes.
"""

import glob
import hashlib
import os
import shutil
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import build_portable  # noqa: E402


@pytest.fixture
def unix_builder(tmp_path, monkeypatch):
    monkeypatch.setattr(build_portable, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(build_portable.platform, "system", lambda: "Linux")
    monkeypatch.setattr(build_portable.platform, "machine", lambda: "x86_64")
    builder = f"{sys.version_info.major}.{sys.version_info.minor}"
    monkeypatch.setattr(build_portable, "STANDALONE_PYTHON", builder + ".99")
    return tmp_path


def test_there_is_no_fallback_that_copies_the_build_machines_python():
    assert not hasattr(build_portable, "_synthesize_local_runtime_archive")
    source = open(os.path.join(REPO_ROOT, "tools", "build_portable.py"), encoding="utf-8").read()
    assert "Falling back to local interpreter" not in source


def test_skip_download_without_a_cached_runtime_stops_the_build(unix_builder):
    with pytest.raises(SystemExit, match="no cached runtime"):
        build_portable.fetch_runtime(skip_download=True)


def test_a_failed_download_stops_the_build(unix_builder, monkeypatch):
    def refuse(url, target):
        raise OSError("HTTP Error 404: Not Found")

    monkeypatch.setattr(build_portable.urllib.request, "urlretrieve", refuse)
    with pytest.raises(SystemExit, match="404"):
        build_portable.fetch_runtime()
    assert not os.listdir(build_portable.CACHE_DIR), "a partial download was left in the cache"


def test_a_runtime_that_does_not_match_its_published_checksum_is_refused(unix_builder, monkeypatch):
    name = build_portable.standalone_runtime_name("Linux", "x86_64")

    def fake_download(url, target):
        if url.endswith("SHA256SUMS"):
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(f"{'0' * 64}  {name}\n")
        else:
            with open(target, "wb") as handle:
                handle.write(b"not the runtime that was published")

    monkeypatch.setattr(build_portable.urllib.request, "urlretrieve", fake_download)
    with pytest.raises(SystemExit, match="checksum"):
        build_portable.fetch_runtime()
    assert not os.path.exists(os.path.join(build_portable.CACHE_DIR, name))


def test_a_runtime_that_matches_its_checksum_is_cached(unix_builder, monkeypatch):
    name = build_portable.standalone_runtime_name("Linux", "x86_64")
    body = b"a runtime archive"
    digest = hashlib.sha256(body).hexdigest()
    seen = []

    def fake_download(url, target):
        seen.append(url)
        if url.endswith("SHA256SUMS"):
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(f"{'1' * 64}  other.tar.gz\n{digest}  {name}\n")
        else:
            with open(target, "wb") as handle:
                handle.write(body)

    monkeypatch.setattr(build_portable.urllib.request, "urlretrieve", fake_download)
    cached = build_portable.fetch_runtime()
    assert os.path.basename(cached) == name
    assert all(build_portable.STANDALONE_RELEASE in url for url in seen)
    assert any(url.endswith("/" + name.replace("+", "%2B")) or url.endswith("/" + name) for url in seen)


def test_the_pin_names_one_exact_build():
    assert build_portable.STANDALONE_PYTHON.count(".") == 2
    assert build_portable.STANDALONE_RELEASE.isdigit() and len(build_portable.STANDALONE_RELEASE) == 8
    name = build_portable.standalone_runtime_name("Darwin", "arm64")
    assert name == (f"cpython-{build_portable.STANDALONE_PYTHON}+{build_portable.STANDALONE_RELEASE}"
                    "-aarch64-apple-darwin-install_only.tar.gz")


def test_a_runtime_for_another_python_is_refused(unix_builder, monkeypatch):
    monkeypatch.setattr(build_portable, "STANDALONE_PYTHON", "3.1.0")
    with pytest.raises(SystemExit, match="ABI"):
        build_portable.fetch_runtime(skip_download=True)


def test_the_release_workflows_pin_the_same_python():
    for workflow in ("release.yml", "desktop.yml"):
        with open(os.path.join(REPO_ROOT, ".github", "workflows", workflow), encoding="utf-8") as handle:
            text = handle.read()
        assert f'python-version: "{build_portable.STANDALONE_PYTHON}"' in text, workflow


@pytest.mark.skipif(sys.platform == "win32", reason="the borrowed library case is the Unix one")
def test_a_runtime_that_borrows_the_hosts_library_is_refused(tmp_path):
    """The measured defect: a binary copied out of the build machine's Python."""
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    shutil.copy2(sys.executable, runtime / "bin" / "python3")
    with pytest.raises(SystemExit, match="not self-contained"):
        build_portable.assert_runtime_self_contained(str(runtime))


def _standalone_on_this_machine():
    pattern = os.path.expanduser(
        f"~/.local/share/uv/python/cpython-{sys.version_info.major}.{sys.version_info.minor}.*-linux-x86_64-gnu")
    found = [path for path in glob.glob(pattern) if not os.path.islink(path)]
    return found[0] if found else None


@pytest.mark.skipif(_standalone_on_this_machine() is None,
                    reason="no python-build-standalone runtime for this Python on this machine")
def test_a_relocated_standalone_runtime_passes(tmp_path):
    runtime = tmp_path / "moved" / "runtime"
    shutil.copytree(_standalone_on_this_machine(), runtime, symlinks=True)
    build_portable.write_path_file(str(runtime))
    report = build_portable.assert_runtime_self_contained(str(runtime))
    assert report["version"].startswith(f"{sys.version_info.major}.{sys.version_info.minor}.")


@pytest.mark.skipif(sys.platform == "win32", reason="the Unix runtime layout")
def test_no_pyvenv_cfg_ties_the_runtime_to_the_working_directory(tmp_path, monkeypatch):
    """
    "home = ." was read relative to wherever the launcher started, and the
    staged interpreter warned "Could not find platform dependent libraries".
    """
    monkeypatch.setattr(build_portable.platform, "system", lambda: "Linux")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    build_portable.write_path_file(str(runtime))
    assert not (runtime / "pyvenv.cfg").exists()


def test_every_command_line_keeps_the_user_site_out():
    """The pyvenv.cfg also switched the user site off; -s does that now."""
    backend = open(os.path.join(REPO_ROOT, "desktop", "src-tauri", "src", "backend.rs"), encoding="utf-8").read()
    assert '.arg("-s")\n        .arg("-m")' in backend
    assert '"$PYTHON_EXE" -s -m studio.cli' in build_portable.UNIX_CLI_LAUNCHER
