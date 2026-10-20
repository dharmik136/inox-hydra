"""
A release is published whole or not at all. [INS-04]

release.yml and desktop.yml each attached files to the tag's release on their
own, and desktop.yml with fail_on_unmatched_files: false. On the next tag the
portable smoke test failed (INS-01) while the desktop job attached its
installer, so a public "latest" release would have held an installer and no
ZIP and no latest.json, and every update check would have answered 404.

Now desktop.yml only builds, release.yml calls it, and one publish job, which
needs every build, checks the set, creates a draft, uploads, confirms the
upload and only then makes the release public.

These read the workflow text, so they run where PyYAML is not installed; the
last one also parses it where PyYAML is.

Strict Invariants:
- Zero em-dashes.
"""

import os
import re
import shutil
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOWS = os.path.join(REPO_ROOT, ".github", "workflows")


def _read(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as handle:
        return handle.read()


def _job(workflow, name):
    """The text of one top level job, up to the next one."""
    start = workflow.index(f"\n  {name}:\n")
    following = re.search(r"\n  [a-z][a-z-]*:\n", workflow[start + 1:])
    return workflow[start: start + 1 + following.start()] if following else workflow[start:]


def _step(job, name):
    start = job.index(f"- name: {name}")
    following = job.find("- name:", start + 1)
    return job[start: following if following != -1 else len(job)]


def test_only_one_workflow_publishes():
    for name in os.listdir(WORKFLOWS):
        text = _read(name)
        if name == "release.yml":
            continue
        assert "action-gh-release" not in text, f"{name} attaches files to a release itself"
        assert not re.search(r"\bgh release\b", text), f"{name} touches a release itself"
        assert not re.search(r"^\s*contents:\s*write", text, re.MULTILINE), f"{name} can write releases"


def test_the_desktop_build_no_longer_runs_on_a_tag_by_itself():
    desktop = _read("desktop.yml")
    on = desktop[desktop.index("\non:"):desktop.index("\npermissions:")]
    assert "workflow_call:" in on
    assert "tags:" not in on, "desktop.yml would build and race the release on every tag"
    assert "uses: ./.github/workflows/desktop.yml" in _read("release.yml")


def test_the_publish_job_needs_every_build_and_runs_only_on_a_tag():
    publish = _job(_read("release.yml"), "publish")
    assert re.search(r"needs:\s*\[build-portable,\s*build-desktop\]", publish)
    assert "if: startsWith(github.ref, 'refs/tags/v')" in publish
    assert "contents: write" in publish


def test_the_set_is_checked_before_anything_exists_on_github():
    publish = _job(_read("release.yml"), "publish")
    check = _step(publish, "Check The Asset Set Is Complete")
    for required in ("-win64.zip", "latest.json", "-win64-setup.exe", "exit 1"):
        assert required in check, f"the completeness check does not require {required}"
    assert publish.index("Check The Asset Set Is Complete") < publish.index("gh release create")


def test_the_release_is_a_draft_until_every_asset_is_confirmed():
    publish = _job(_read("release.yml"), "publish")
    create = _step(publish, "Create The Release As A Draft")
    assert "gh release create" in create and "--draft" in create
    assert "already a published release" in create, "a rerun could replace a live release"
    confirm = publish.index("Confirm Every Asset Reached The Draft")
    go_live = publish.index("--draft=false")
    assert publish.index("gh release create") < confirm < go_live
    assert publish.rstrip().endswith("--latest"), "making the release public is not the last step"


def test_previews_are_built_but_never_collected_for_the_release():
    desktop = _read("desktop.yml")
    assert re.search(r"os: windows-latest\s+release: true", desktop)
    assert re.search(r"os: macos-latest\s+release: false", desktop)
    assert re.search(r"os: ubuntu-latest\s+release: false", desktop)
    assert "continue-on-error: ${{ !matrix.release }}" in desktop
    assert "name: preview-desktop-${{ matrix.os }}" in desktop
    assert "name: release-desktop-windows" in desktop
    assert "pattern: release-*" in _job(_read("release.yml"), "publish")
    assert "LinkedIn-Studio-" not in desktop


def test_the_installer_is_published_under_a_name_without_spaces():
    """GitHub rewrites spaces in asset names, so the updater URL would 404."""
    desktop = _read("desktop.yml")
    assert "InoxHydra-$version-win64-setup.exe" in desktop
    manifest = _step(desktop, "Build The Update Manifest")
    assert "GetFileName($installer)" in manifest
    assert '"desktop/dist/latest-desktop.json"' in manifest


def test_the_portable_job_hands_over_the_zip_and_latest_json():
    portable = _job(_read("release.yml"), "build-portable")
    gather = _step(portable, "Gather The Release Files")
    assert "cp dist/portable/*.zip dist/release/" in gather
    assert "cp release/latest.json dist/release/" in gather
    upload = _step(portable, "Upload Build Artifact")
    assert "name: release-portable" in upload and "if-no-files-found: error" in upload
    assert portable.index("Smoke Test The Portable Artifact") < portable.index("Upload Build Artifact")


def test_the_workflows_parse():
    yaml = pytest.importorskip("yaml")
    release = yaml.safe_load(_read("release.yml"))
    assert release["jobs"]["publish"]["needs"] == ["build-portable", "build-desktop"]
    assert release["jobs"]["build-desktop"]["uses"] == "./.github/workflows/desktop.yml"
    desktop = yaml.safe_load(_read("desktop.yml"))
    triggers = desktop.get(True, desktop.get("on"))
    assert "workflow_call" in triggers and "push" not in triggers


# ---------------------------------------------------------------------------
# The publish job's own shell, run here against a fake gh. act is not
# available, so the steps are executed as the runner would execute them.
# ---------------------------------------------------------------------------

runs_bash = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"),
                               reason="the publish job runs bash on ubuntu-latest")


def _run_block(step):
    body = step[step.index("run: |\n") + len("run: |\n"):]
    return textwrap.dedent(body)


def _fake_gh(bin_dir, log, state):
    """Records each call; `release view` answers from a state file it keeps."""
    gh = bin_dir / "gh"
    gh.write_text(textwrap.dedent(f'''\
        #!/usr/bin/env bash
        echo "gh $*" >> "{log}"
        state="$(cat "{state}" 2>/dev/null || echo absent)"
        if [ "$1 $2" = "release view" ]; then
          if [ "$state" = "absent" ]; then echo "release not found" >&2; exit 1; fi
          case "$*" in
            *isDraft*) echo "$state" ;;
            *assets*) cat "{state}.assets" ;;
          esac
          exit 0
        fi
        if [ "$1 $2" = "release create" ]; then
          echo true > "{state}"
          for arg in "$@"; do [ -f "$arg" ] && basename "$arg"; done | grep -v '^notes.md$' > "{state}.assets"
          exit 0
        fi
        if [ "$1 $2" = "release delete" ]; then echo absent > "{state}"; exit 0; fi
        if [ "$1 $2" = "release edit" ]; then echo false > "{state}"; exit 0; fi
        exit 0
    '''), encoding="utf-8")
    gh.chmod(0o755)


def _publish(tmp_path, files, state="absent"):
    publish = _job(_read("release.yml"), "publish")
    assets = tmp_path / "assets"
    assets.mkdir()
    for name, body in files.items():
        (assets / name).write_text(body, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log, state_file = tmp_path / "gh.log", tmp_path / "state"
    state_file.write_text(state, encoding="utf-8")
    _fake_gh(bin_dir, log, state_file)
    (tmp_path / "notes.md").write_text("notes", encoding="utf-8")
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "TAG": "v2.6.0", "HOME": str(tmp_path)}
    for name in ("Check The Asset Set Is Complete", "Create The Release As A Draft",
                 "Confirm Every Asset Reached The Draft", "Publish The Draft"):
        step = _step(publish, name)
        script = _run_block(step) if "run: |" in step else step.split("run: ", 1)[1]
        result = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return name, result, log.read_text(encoding="utf-8") if log.exists() else ""
    return None, None, log.read_text(encoding="utf-8")


COMPLETE = {
    "InoxHydra-2.6.0-win64.zip": "zip",
    "latest.json": '{"version": "2.6.0"}',
    "InoxHydra-2.6.0-win64-setup.exe": "exe",
}


@runs_bash
def test_a_complete_set_becomes_one_draft_then_goes_live(tmp_path):
    failed, result, calls = _publish(tmp_path, COMPLETE)
    assert failed is None, (failed, result.stdout, result.stderr)
    assert "gh release create v2.6.0 --draft --verify-tag" in calls
    assert calls.index("release create") < calls.index("release edit v2.6.0 --draft=false --latest")


@runs_bash
@pytest.mark.parametrize("absent", sorted(COMPLETE))
def test_a_missing_asset_stops_before_any_release_exists(tmp_path, absent):
    files = {k: v for k, v in COMPLETE.items() if k != absent}
    failed, result, calls = _publish(tmp_path, files)
    assert failed == "Check The Asset Set Is Complete"
    assert absent in result.stdout
    assert "release create" not in calls


@runs_bash
def test_a_manifest_for_another_version_stops_the_release(tmp_path):
    files = dict(COMPLETE, **{"latest.json": '{"version": "2.5.2"}'})
    failed, result, calls = _publish(tmp_path, files)
    assert failed == "Check The Asset Set Is Complete" and "2.5.2" in result.stdout


@runs_bash
def test_an_updater_manifest_without_its_signature_stops_the_release(tmp_path):
    files = dict(COMPLETE, **{"latest-desktop.json": "{}"})
    failed, result, _ = _publish(tmp_path, files)
    assert failed == "Check The Asset Set Is Complete" and "setup.exe.sig" in result.stdout


@runs_bash
def test_a_published_release_is_never_replaced(tmp_path):
    failed, result, calls = _publish(tmp_path, COMPLETE, state="false")
    assert failed == "Create The Release As A Draft"
    assert "already a published release" in result.stdout
    assert "release delete" not in calls and "release create" not in calls


@runs_bash
def test_a_draft_left_by_a_failed_run_is_replaced(tmp_path):
    failed, _, calls = _publish(tmp_path, COMPLETE, state="true")
    assert failed is None
    assert calls.index("release delete v2.6.0") < calls.index("release create v2.6.0")
