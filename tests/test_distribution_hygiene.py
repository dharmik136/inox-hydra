"""
What Ships
==========
This repository distributes an engine. It must not distribute the person who
built it, or anyone who engaged with them.

Every rule here exists because the class of leak it prevents already happened:

- Two database backups holding 225 real people, 166 real profile URLs and 662
  comment texts were committed, because `.gitignore` covered `studio/data/*.db`
  and the backups were written one directory deeper. Removed in b2c8579.
- `studio/extension.pem`, the key that can sign an update every installed copy
  accepts as genuine, sat untracked and unignored, one `git add -A` away.
- `studio/data/linkedin_studio.db` with 17 real profile URLs is still reachable
  in published history from the initial release commit. That one is recorded in
  the G-Stack rather than fixed here, because removing it means rewriting
  history that other clones already have.

These check the index, not the working tree. A file you have locally is your
business; a file git is tracking is everybody's.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _tracked_files():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        pytest.skip("not a git repository")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


# Extensions that carry captured data or the means to impersonate this software.
FORBIDDEN_SUFFIXES = (
    ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3",
    ".pem", ".key", ".crx", ".pfx", ".p12",
)

# Paths that are allowed to exist under a data directory.
DATA_DIR_ALLOWLIST = {"studio/data/.gitkeep"}


def test_no_database_or_key_file_is_tracked():
    """
    The two classes that actually leaked: a database full of real people, and
    the extension signing key.
    """
    offenders = [
        f for f in _tracked_files()
        if f.lower().endswith(FORBIDDEN_SUFFIXES)
    ]
    assert not offenders, (
        "These files carry captured data or signing material and must not be "
        "tracked:\n  " + "\n  ".join(offenders)
    )


def test_the_data_directory_ships_empty():
    """
    `studio/data/` is where the creator's own database, media and vault live. It
    ships as an empty directory and nothing else.
    """
    offenders = [
        f for f in _tracked_files()
        if f.startswith("studio/data/") and f not in DATA_DIR_ALLOWLIST
    ]
    assert not offenders, (
        "studio/data/ should contain only .gitkeep. Tracked:\n  "
        + "\n  ".join(offenders)
    )


def test_no_backup_directory_is_tracked():
    """
    The specific shape of the leak: backups written one directory below the
    ignore rule. Checked by path rather than by extension, because a backup is
    dangerous whatever it is named.
    """
    offenders = [
        f for f in _tracked_files()
        if "/backups/" in f or f.startswith("backups/")
    ]
    assert not offenders, (
        "Backups hold the same real people the live database does:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("pattern", [
    "studio/data/backups/",
    "studio/data/linkedin_studio.db",
    "studio/extension.pem",
    "studio/data/media/",
])
def test_the_sensitive_paths_are_ignored(pattern):
    """
    Ignored, not merely absent. A path that is untracked today but unignored is
    one `git add -A` from being tracked tomorrow, which is exactly how the
    backups were committed.
    """
    probe = os.path.join(REPO_ROOT, pattern.rstrip("/"))
    if pattern.endswith("/"):
        probe = os.path.join(probe, "probe.db")

    result = subprocess.run(
        ["git", "check-ignore", "-q", probe],
        cwd=REPO_ROOT, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"{pattern} is not covered by .gitignore. Anything written there would "
        f"be picked up by `git add -A`."
    )


def test_no_captured_leads_appear_in_tracked_text():
    """
    A person's LinkedIn profile URL is the identifying half of every row this
    product captures. None should appear in tracked source, documentation or
    fixtures outside of obvious placeholders.
    """
    result = subprocess.run(
        ["git", "grep", "-l", "-E", r"linkedin\.com/in/[a-z0-9]", "--", "."],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    files = [f.strip() for f in result.stdout.splitlines() if f.strip()]

    # Tests and the extension legitimately construct or match profile URLs.
    allowed_prefixes = ("tests/", "studio/extension/", "docs/")

    # Not captured data, and each is filed or legitimate:
    #   database.py    the four fabricated sample leads, G-Stack #246
    #   linkedin_client.py  a mock fixture used only by tests
    #   index.html     a placeholder attribute on an input
    known_non_captured = {
        "studio/backend/database.py",
        "studio/backend/linkedin_client.py",
        "studio/frontend/index.html",
    }
    offenders = [
        f for f in files
        if not f.startswith(allowed_prefixes) and f not in known_non_captured
    ]

    assert not offenders, (
        "Real profile URLs may have reached tracked files:\n  "
        + "\n  ".join(offenders)
    )


# Personal media the author generated for their own posts. Not an engine
# artifact, and 4.6MB of it. Frozen rather than banned, because removing it is a
# product decision (the docs reference these images), but a new one should be a
# deliberate act rather than an accident.
KNOWN_PERSONAL_ASSETS = 6


def test_personal_media_does_not_accumulate():
    """
    Ratchet. These images are the author's own career graphics, referenced only
    from documentation. They are not part of the engine, and a repository that
    distributes an engine should not grow more of them.
    """
    media = [
        f for f in _tracked_files()
        if f.startswith("assets/")
        and f.lower().endswith((".jpg", ".jpeg", ".png", ".pdf", ".mp4", ".webp"))
    ]
    assert len(media) <= KNOWN_PERSONAL_ASSETS, (
        f"assets/ now tracks {len(media)} media files, up from the frozen "
        f"ceiling of {KNOWN_PERSONAL_ASSETS}. These are personal content rather "
        f"than engine code. If you removed some, lower the ceiling."
    )

# ---------------------------------------------------------------------------
# What the BUILD copies, as opposed to what git tracks
#
# The tests above check the index, which is the right boundary for git and the
# wrong one for a build. copy_application reads the working tree, so a file
# that is correctly gitignored and correctly absent from a CI checkout is still
# sitting beside the source on the machine of whoever runs a local build, and
# was being copied straight into the distributable.
#
# That is how studio/extension.pem, the key that signs an update every
# installed copy accepts as genuine, ended up in a locally built payload.
# ---------------------------------------------------------------------------

def _build_portable():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_portable", os.path.join(REPO_ROOT, "tools", "build_portable.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_build_excludes_the_extension_signing_key():
    """
    The key that can push code to every installed copy must not be copyable
    into an artifact, whether or not it happens to be present locally.
    """
    build = _build_portable()
    assert "*.pem" in build.SECRET_PATTERNS
    assert "*.key" in build.SECRET_PATTERNS
    assert "*.pfx" in build.SECRET_PATTERNS


def test_a_staged_private_key_stops_the_build():
    """
    The ignore patterns are the first line. This is the second, because the
    cost of being wrong is unbounded and the cost of the check is a walk.
    """
    build = _build_portable()

    staged = pathlib.Path(tempfile.mkdtemp(prefix="inox_hygiene_")) / "staged"
    (staged / "studio").mkdir(parents=True)
    (staged / "studio" / "extension.pem").write_text(
        "-----BEGIN PRIVATE KEY-----\nnot a real key\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as caught:
        build.assert_no_secrets(str(staged))

    message = str(caught.value)
    assert "extension.pem" in message
    assert "REFUSING TO BUILD" in message


def test_the_public_ca_bundle_is_not_mistaken_for_a_secret():
    """
    certifi ships cacert.pem, the public trust roots every HTTPS request
    depends on. It has the same extension as a private key and must still
    ship, so the two are told apart on content rather than on the name.
    """
    build = _build_portable()

    staged = pathlib.Path(tempfile.mkdtemp(prefix="inox_hygiene_")) / "staged"
    (staged / "lib" / "certifi").mkdir(parents=True)
    (staged / "lib" / "certifi" / "cacert.pem").write_text(
        "-----BEGIN CERTIFICATE-----\npublic trust root\n-----END CERTIFICATE-----\n",
        encoding="utf-8",
    )

    # Must not raise. Refusing this would break outbound HTTPS in the artifact.
    build.assert_no_secrets(str(staged))


def test_both_build_paths_run_the_secret_check():
    """
    The portable ZIP and the desktop installer carry the same payload. A check
    on only one of them protects only one of them.
    """
    builder = open(os.path.join(REPO_ROOT, "tools", "build_portable.py"), encoding="utf-8").read()
    staging = open(os.path.join(REPO_ROOT, "tools", "stage_desktop_payload.py"), encoding="utf-8").read()

    assert "assert_no_secrets(target)" in builder, "the portable build does not verify what it staged"
    assert "assert_no_secrets(PAYLOAD_ROOT)" in staging, "the desktop payload is not verified"

