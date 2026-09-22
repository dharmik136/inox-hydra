"""
P6 Verification Suite: Self-Service Support Without A Support Channel.
=====================================================================
These cover the tools a user has to operate alone, because nobody can log into
their machine.

The redaction tests are the important ones, and they are written as security
tests rather than formatting tests. The diagnostics bundle is designed to be
pasted into a public GitHub issue, and the database it reads holds the user's
LinkedIn session cookies and their AI provider API key. Every test here plants
real-looking secrets and then proves they are absent from the output, rather
than asserting that a redaction function was called.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import migrations, paths, support, updates  # noqa: E402

LI_AT = "AQEDA_notarealkey_LINKEDIN_COOKIE_zzz999"
JSESSIONID = "ajax:1234567890123456789"
API_KEY = "sk-proj-notarealkey-DO-NOT-LEAK-8888"

SECRETS = (LI_AT, JSESSIONID, API_KEY)


@pytest.fixture
def installation(monkeypatch):
    """A populated installation with real-looking credentials stored."""
    home = tempfile.mkdtemp(prefix="inox_support_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)

    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("CREATE TABLE drafts (id INTEGER PRIMARY KEY, title TEXT, content TEXT)")
    conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT)")
    for key, value in (("li_at", LI_AT), ("JSESSIONID", JSESSIONID),
                       ("ai_api_key", API_KEY), ("ai_provider", "openai"),
                       ("ai_model", "gpt-4o")):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.execute("INSERT INTO drafts (title, content) VALUES (?, ?)",
                 ("A draft", "months of work"))
    conn.execute("INSERT INTO leads (name) VALUES (?)", ("A prospect",))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    yield home
    shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# Redaction. These are security tests.
# ---------------------------------------------------------------------------

def test_diagnostics_never_contain_credentials(installation):
    """The bundle is meant to be posted in public. Prove it is safe to."""
    report = support.collect_diagnostics()
    serialized = json.dumps(report, default=str)
    for secret in SECRETS:
        assert secret not in serialized, f"diagnostics leaked {secret[:16]}..."


def test_written_bundle_never_contains_credentials(installation):
    """Same guarantee against the file on disk, which is what a user attaches."""
    path = support.write_diagnostics_bundle()
    with open(path, encoding="utf-8") as f:
        contents = f.read()
    for secret in SECRETS:
        assert secret not in contents, f"bundle file leaked {secret[:16]}..."


def test_redaction_is_an_allowlist_not_a_denylist(installation):
    """
    The property that makes this hold as the product grows.

    A denylist fails open: a new credential key added later would leak until
    somebody remembered to list it. An unknown key must be redacted by default.
    """
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)",
                 ("some_future_oauth_secret", "TOTALLY_SECRET_FUTURE_VALUE"))
    conn.commit()
    conn.close()

    report = support.collect_diagnostics()
    assert "TOTALLY_SECRET_FUTURE_VALUE" not in json.dumps(report, default=str)
    entry = report["settings"]["some_future_oauth_secret"]
    assert entry["redacted"] is True


def test_redaction_still_reports_whether_a_value_is_set(installation):
    """
    Redaction must not destroy the diagnostic signal.

    "the key is missing" and "the key is set but wrong" are different bugs, and
    we have to tell them apart without ever seeing the value.
    """
    report = support.collect_diagnostics()
    entry = report["settings"]["ai_api_key"]
    assert entry["redacted"] is True
    assert entry["is_set"] is True
    assert entry["length"] == len(API_KEY)


def test_allowlisted_settings_are_readable(installation):
    """Non-sensitive configuration must survive, or the bundle is useless."""
    report = support.collect_diagnostics()
    assert report["settings"]["ai_provider"] == "openai"
    assert report["settings"]["ai_model"] == "gpt-4o"


def test_export_excludes_credentials(installation):
    """An export is content, not credentials. It is shared more casually."""
    path = support.export_data(fmt="json")
    with open(path, encoding="utf-8") as f:
        contents = f.read()
    for secret in SECRETS:
        assert secret not in contents, f"export leaked {secret[:16]}..."
    assert "settings" not in json.load(open(path, encoding="utf-8"))["tables"]


# ---------------------------------------------------------------------------
# Backup, restore, export, reset
# ---------------------------------------------------------------------------

def test_backup_contains_a_restorable_database(installation):
    archive = support.create_backup("test")
    assert os.path.exists(archive)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
    assert "data/linkedin_studio.db" in names
    assert "backup_manifest.json" in names

    info = support.inspect_backup(archive)
    assert info["has_database"]
    assert info["manifest"]["app_version"]


def test_restore_recovers_destroyed_data(installation):
    """The whole point. A user destroys their work and gets it back."""
    archive = support.create_backup("before")

    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("DELETE FROM drafts")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 0
    conn.close()

    result = support.restore_backup(archive)

    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 1
    assert conn.execute("SELECT content FROM drafts").fetchone()[0] == "months of work"
    conn.close()
    assert result["safety_backup"], "restoring did not snapshot the current state first"


def test_restore_snapshots_current_state_before_overwriting(installation):
    """
    Restoring the wrong archive must be survivable. Without this, a mistaken
    restore is the one failure nobody can rescue the user from.
    """
    archive = support.create_backup("first")
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO drafts (title, content) VALUES (?, ?)", ("later", "newer work"))
    conn.commit()
    conn.close()

    result = support.restore_backup(archive)
    safety = result["safety_backup"]
    assert safety and os.path.exists(safety)

    # The safety snapshot holds the state that the restore replaced.
    with zipfile.ZipFile(safety) as z:
        recovered = tempfile.mkdtemp(prefix="inox_safety_")
        z.extract("data/linkedin_studio.db", recovered)
        conn = sqlite3.connect(os.path.join(recovered, "data", "linkedin_studio.db"))
        titles = {r[0] for r in conn.execute("SELECT title FROM drafts")}
        conn.close()
    shutil.rmtree(recovered, ignore_errors=True)
    assert "later" in titles, "safety snapshot did not capture the pre-restore state"


def test_restore_refuses_an_archive_with_no_database(installation):
    bogus = os.path.join(paths.get_backups_dir(), "not_a_backup.zip")
    with zipfile.ZipFile(bogus, "w") as z:
        z.writestr("readme.txt", "nothing useful here")
    with pytest.raises(ValueError, match="no database"):
        support.restore_backup(bogus)


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_export_produces_readable_content(installation, fmt):
    path = support.export_data(fmt=fmt)
    assert os.path.exists(path) and os.path.getsize(path) > 0
    if fmt == "json":
        payload = json.load(open(path, encoding="utf-8"))
        assert "drafts" in payload["tables"]
        assert payload["tables"]["drafts"][0]["content"] == "months of work"
    else:
        with zipfile.ZipFile(path) as z:
            assert "drafts.csv" in z.namelist()
            assert b"months of work" in z.read("drafts.csv")


def test_reset_clears_config_but_keeps_content(installation):
    result = support.reset_configuration(keep_data=True)

    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 1, (
        "reset destroyed user content"
    )
    conn.close()
    assert result["safety_backup"]


def test_destructive_reset_is_not_implemented(installation):
    """Deliberately absent. There is no undo for it and no support channel."""
    with pytest.raises(NotImplementedError):
        support.reset_configuration(keep_data=False)


# ---------------------------------------------------------------------------
# Opt-in update checks
# ---------------------------------------------------------------------------

def test_update_checks_are_off_by_default(installation):
    assert updates.is_enabled() is False
    assert updates.has_been_asked() is False


def test_disabled_check_makes_no_network_request(installation, monkeypatch):
    """
    The zero egress promise, enforced rather than documented.

    Any attempt to reach the network while disabled fails the test loudly.
    """
    import requests

    def explode(*args, **kwargs):
        raise AssertionError("a network request was made while update checks were disabled")

    monkeypatch.setattr(requests, "get", explode)

    result = updates.check_for_update()
    assert result["checked"] is False
    assert result["enabled"] is False
    assert "Nothing was sent" in result["reason"]


def test_preference_round_trips(installation):
    updates.set_enabled(True)
    assert updates.is_enabled() is True
    assert updates.has_been_asked() is True
    updates.set_enabled(False)
    assert updates.is_enabled() is False
    assert updates.has_been_asked() is True, "opting out must still count as answered"


@pytest.mark.parametrize("remote,local,expected", [
    ("2.6.0", "2.5.0", True),
    ("2.5.1", "2.5.0", True),
    ("2.10.0", "2.9.0", True),     # numeric, not lexical
    ("2.5.0", "2.5.0", False),
    ("2.4.9", "2.5.0", False),
    ("10.0.0", "9.99.99", True),
])
def test_version_comparison(remote, local, expected):
    assert updates.is_newer(remote, local) is expected


def test_malformed_remote_version_does_not_crash():
    """The manifest is untrusted input. It must never take down startup."""
    assert updates.parse_version("not-a-version") == (0,)
    assert updates.parse_version("") == (0,)
    assert updates.is_newer("garbage", "2.5.0") is False


def test_update_check_reports_but_never_installs():
    """
    A guard on intent. This module must not gain the ability to fetch and run
    an update, because a failed self update on an unreachable machine is
    unrecoverable.
    """
    source = open(os.path.join(os.path.dirname(__file__), "..", "studio", "backend",
                               "updates.py"), encoding="utf-8").read()
    for forbidden in ("subprocess", "os.system", "shutil.unpack_archive",
                      "zipfile.ZipFile", "exec(", "eval("):
        assert forbidden not in source, (
            f"updates.py references {forbidden!r}. This module reports versions, "
            "it must never install anything."
        )


def test_schema_status_is_included_in_diagnostics(installation):
    """Schema state is the first thing to check when an upgrade goes wrong."""
    report = support.collect_diagnostics()
    assert report["schema"]["current_version"] == migrations.BASELINE_VERSION
    assert "target_version" in report["schema"]
