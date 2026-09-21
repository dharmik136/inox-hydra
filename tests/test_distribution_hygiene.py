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
import subprocess

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
