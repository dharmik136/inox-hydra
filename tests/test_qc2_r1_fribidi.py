"""
The Windows builds carry FriBiDi, so Hindi and Gujarati overlays are laid out. [R7-N1]

Pillow's Windows wheels include raqm, the complex text layout engine, but not
FriBiDi, which raqm loads at run time (Pillow looks for fribidi.dll,
fribidi-0.dll or libfribidi-0.dll in the DLL search order). Without it
PIL.features.check("raqm") is False and the image studio leaves Devanagari and
Gujarati quote overlays off generated images (found by batch R7).

The build now copies a FriBiDi DLL beside the bundled python.exe, with its
LGPL licence, and refuses a Windows runtime in which raqm does not load.
CI builds the DLL with the runner's vcpkg (release.yml, desktop.yml, ci.yml).

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
import types

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import build_portable  # noqa: E402


@pytest.fixture
def windows(monkeypatch, tmp_path):
    monkeypatch.setattr(build_portable.platform, "system", lambda: "Windows")
    monkeypatch.setattr(build_portable, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("INOX_FRIBIDI_DLL", raising=False)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    return runtime


def _vcpkg_layout(tmp_path):
    bin_dir = tmp_path / "vcpkg" / "installed" / "x64-windows" / "bin"
    bin_dir.mkdir(parents=True)
    dll = bin_dir / "fribidi-0.dll"
    dll.write_bytes(b"MZ fake dll")
    share = tmp_path / "vcpkg" / "installed" / "x64-windows" / "share" / "fribidi"
    share.mkdir(parents=True)
    (share / "copyright").write_text("GNU LESSER GENERAL PUBLIC LICENSE", encoding="utf-8")
    return dll


def test_a_windows_build_without_fribidi_is_refused(windows):
    with pytest.raises(SystemExit, match="FriBiDi"):
        build_portable.bundle_fribidi(str(windows))


def test_the_dll_lands_beside_python_exe_with_its_licence(windows, tmp_path, monkeypatch):
    dll = _vcpkg_layout(tmp_path)
    monkeypatch.setenv("INOX_FRIBIDI_DLL", str(dll))
    placed = build_portable.bundle_fribidi(str(windows))
    assert placed == str(windows / "fribidi-0.dll")
    assert (windows / "fribidi-0.dll").read_bytes() == b"MZ fake dll"
    assert "LESSER GENERAL PUBLIC" in (windows / "FRIBIDI-LICENSE.txt").read_text(encoding="utf-8")


def test_a_dll_without_its_licence_is_refused(windows, tmp_path, monkeypatch):
    dll = _vcpkg_layout(tmp_path)
    os.remove(tmp_path / "vcpkg" / "installed" / "x64-windows" / "share" / "fribidi" / "copyright")
    monkeypatch.setenv("INOX_FRIBIDI_DLL", str(dll))
    with pytest.raises(SystemExit, match="licence"):
        build_portable.bundle_fribidi(str(windows))


def test_other_platforms_need_nothing_extra(monkeypatch, tmp_path):
    """Pillow's Linux and macOS wheels carry FriBiDi themselves."""
    monkeypatch.setattr(build_portable.platform, "system", lambda: "Linux")
    assert build_portable.bundle_fribidi(str(tmp_path)) is None


def _fake_probe(monkeypatch, stdout, returncode=0):
    monkeypatch.setattr(build_portable, "get_runtime_interpreter", lambda runtime: "python")
    monkeypatch.setattr(build_portable.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr="boom"))


def test_a_windows_runtime_where_raqm_does_not_load_is_refused(windows, monkeypatch):
    _fake_probe(monkeypatch, '{"raqm": false, "fribidi": null}\n')
    with pytest.raises(SystemExit, match="raqm"):
        build_portable.assert_complex_text_layout(str(windows))


def test_a_windows_runtime_where_raqm_loads_passes(windows, monkeypatch):
    _fake_probe(monkeypatch, '{"raqm": true, "fribidi": "1.0.13"}\n')
    assert build_portable.assert_complex_text_layout(str(windows))["raqm"] is True


def test_the_probe_really_asks_pillow():
    assert 'features.check("raqm")' in build_portable._TEXT_LAYOUT_PROBE


def test_both_builders_and_every_windows_build_job_provide_it():
    import inspect

    assert "bundle_fribidi(runtime_dir)" in inspect.getsource(build_portable.main)
    assert "assert_complex_text_layout(runtime_dir)" in inspect.getsource(build_portable.main)
    with open(os.path.join(REPO_ROOT, "tools", "stage_desktop_payload.py"), encoding="utf-8") as handle:
        staging = handle.read()
    assert "build_portable.bundle_fribidi(runtime_dir)" in staging
    assert "build_portable.assert_complex_text_layout(runtime_dir)" in staging
    for workflow in ("release.yml", "desktop.yml", "ci.yml"):
        with open(os.path.join(REPO_ROOT, ".github", "workflows", workflow), encoding="utf-8") as handle:
            text = handle.read()
        assert "vcpkg.exe\" install fribidi:x64-windows" in text, workflow
        assert "INOX_FRIBIDI_DLL=" in text, workflow


@pytest.mark.skipif(sys.platform == "win32", reason="the real probe here is the Unix one")
def test_the_real_probe_runs_against_this_interpreter(tmp_path, monkeypatch):
    monkeypatch.setattr(build_portable, "get_runtime_interpreter", lambda runtime: sys.executable)
    report = build_portable.assert_complex_text_layout(str(tmp_path))
    assert set(report) == {"raqm", "fribidi"}
