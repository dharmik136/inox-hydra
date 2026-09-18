"""
P5 Verification Suite: The Portable Build Is Configured Correctly.
==================================================================
Fast guards that run on every commit. Actually building and booting the 40 MB
artifact is the job of tools/build_portable.py plus tools/smoke_portable.py on
the release workflow.

What these protect, all of which fail silently rather than loudly:

  - Shipping an `app/studio/data` directory. Its absence is the single thing
    that routes user state to the profile directory. If it ever appears in the
    artifact, every update destroys the user's drafts and leads, and nothing
    about the build would look wrong.
  - Building the Windows artifact on a Linux runner. The ZIP embeds compiled
    wheels, so it would produce a distributable that cannot import its own
    dependencies, and the build would still report success.
  - A launcher that invokes a bare `python`, which would work on the developer's
    machine and fail on a machine with no Python, which is the entire audience.
  - Releasing a tag that disagrees with the declared version.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import re

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILDER = os.path.join(REPO_ROOT, "tools", "build_portable.py")
SMOKE = os.path.join(REPO_ROOT, "tools", "smoke_portable.py")
RELEASE_WORKFLOW = os.path.join(REPO_ROOT, ".github", "workflows", "release.yml")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def builder():
    return read(BUILDER)


@pytest.fixture(scope="module")
def workflow():
    return read(RELEASE_WORKFLOW)


def test_build_tooling_exists():
    for path in (BUILDER, SMOKE, RELEASE_WORKFLOW):
        assert os.path.exists(path), f"missing {os.path.relpath(path, REPO_ROOT)}"


def test_user_state_directory_is_excluded_from_the_artifact(builder):
    """
    The highest consequence line in the whole build. Shipping studio/data makes
    the application write state inside the folder an update replaces.
    """
    match = re.search(r"STUDIO_EXCLUDE\s*=\s*\{([^}]*)\}", builder)
    assert match, "STUDIO_EXCLUDE is not defined"
    excluded = {part.strip().strip('"\'') for part in match.group(1).split(",")}
    for required in ("data", "assets", "tests", "__pycache__"):
        assert required in excluded, f"{required!r} is not excluded from the artifact"


def test_builder_asserts_the_data_directory_is_absent(builder):
    """Belt and braces: the build must fail loudly if the exclusion ever regresses."""
    assert 'os.path.join(target, "data")' in builder
    assert "assert not os.path.exists" in builder


def test_smoke_test_rejects_an_artifact_containing_user_state():
    """The same check again at the far end, against the real built ZIP."""
    smoke = read(SMOKE)
    assert '"app", "studio", "data"' in smoke
    assert "would then destroy that data" in smoke or "destroy that data" in smoke


def test_path_file_exposes_lib_and_app(builder):
    """
    The embeddable interpreter sees nothing by default. Without these entries
    it cannot import either the vendored dependencies or the application.
    """
    assert "..\\\\lib" in builder or r"..\lib" in builder
    assert "..\\\\app" in builder or r"..\app" in builder
    assert "import site" in builder, "pip installed distributions need site enabled"


def test_launcher_uses_the_bundled_interpreter(builder):
    """A bare `python` would work here and fail on the target audience's machine."""
    match = re.search(r'LAUNCHER = r"""(.*?)"""', builder, re.DOTALL)
    assert match, "LAUNCHER template not found"
    launcher = match.group(1)

    assert r"%~dp0runtime\python.exe" in launcher, "launcher does not use the bundled runtime"
    assert "studio.backend.app:app" in launcher
    assert "127.0.0.1" in launcher, "server must bind loopback only"
    assert not re.search(r"^\s*start .*[^\\]\bpython(w)?\.exe", launcher, re.MULTILINE), (
        "launcher appears to invoke a system interpreter"
    )


def test_readme_tells_the_user_where_their_data_lives(builder):
    match = re.search(r'README = """(.*?)"""', builder, re.DOTALL)
    assert match, "README template not found"
    readme = match.group(1)
    assert "LOCALAPPDATA" in readme
    assert "backups" in readme.lower()
    assert "UPGRADING" in readme, "the upgrade procedure must be stated in the artifact itself"


def test_release_workflow_builds_on_windows(workflow):
    """
    Compiled wheels are ABI specific. A Linux runner would produce a ZIP that
    cannot import pymupdf, pillow or pydantic-core, and would still pass.
    """
    assert "runs-on: windows-latest" in workflow, (
        "the portable artifact must be built on a Windows runner"
    )
    assert "ubuntu" not in workflow.lower(), "a Linux runner would produce a broken artifact"


def test_release_workflow_gates_on_verification(workflow):
    """A release must not be publishable without the build actually being exercised."""
    for required in ("tools/sync_version.py --check",
                     "tools/verify_package.py",
                     "tools/smoke_portable.py",
                     "pytest tests"):
        assert required in workflow, f"release workflow does not run {required}"


def test_release_workflow_refuses_a_mismatched_tag(workflow):
    """Shipping v2.6.0 from a tree declaring 2.5.0 makes every bug report useless."""
    assert "does not match studio/__version__.py" in workflow
    assert "exit 1" in workflow


def test_release_workflow_is_valid_yaml(workflow):
    yaml = pytest.importorskip("yaml", reason="pyyaml not installed")
    parsed = yaml.safe_load(workflow)
    assert "jobs" in parsed
    job = parsed["jobs"]["build-portable"]
    assert job["runs-on"] == "windows-latest"
    assert any("build_portable.py" in str(step.get("run", "")) for step in job["steps"])
