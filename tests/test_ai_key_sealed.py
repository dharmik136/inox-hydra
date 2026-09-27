"""
The AI Key Is Sealed At Rest
============================
The LinkedIn session cookies have gone through the vault since it existed. The
AI provider key never did: save_ai_config wrote it into the settings table as
typed, four readers took it back out the same way, and the README called that
table an "encrypted vault". The help article on what leaves this machine had
to tell people plainly that it was not.

These guards hold the change from both ends: what is in the file, and what the
studio can still do with it.

The fixture key is built at run time so no credential-shaped literal sits in
this file; tests/test_distribution_hygiene.py rejects one.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import secret_settings  # noqa: E402
from database import get_db  # noqa: E402
from agno_agentos.model_gateway import get_current_ai_config, save_ai_config  # noqa: E402

FAKE_KEY = "fixture." + "7" * 32


def _raw(key):
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _write_raw(key, value):
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                     (key, value))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def restore_ai_settings():
    """Every test here writes the AI settings; hand the table back as found."""
    conn = get_db()
    try:
        saved = conn.execute("SELECT key, value FROM settings WHERE key LIKE 'ai_%' OR key = 'gemini_api_key'").fetchall()
    finally:
        conn.close()
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM settings WHERE key LIKE 'ai_%' OR key = 'gemini_api_key'")
        conn.executemany("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                         [(row[0], row[1]) for row in saved])
        conn.commit()
    finally:
        conn.close()


def test_a_saved_key_is_not_in_the_file_as_typed():
    save_ai_config(provider="openai", api_key=FAKE_KEY, model="gpt-4o-mini")
    stored = _raw("ai_api_key")
    assert stored and stored != FAKE_KEY, "the key is stored as typed"
    assert FAKE_KEY not in stored, "the key is visible inside the stored value"
    assert secret_settings.is_sealed(stored), f"the stored value carries no seal: {stored[:12]}..."


def test_the_studio_still_reads_the_key_it_saved():
    save_ai_config(provider="openai", api_key=FAKE_KEY, model="gpt-4o-mini")
    assert get_current_ai_config().api_key == FAKE_KEY


def test_the_legacy_gemini_copy_is_sealed_too():
    """
    save_ai_config writes a second copy under gemini_api_key for the older
    readers. Sealing one and not the other would leave the key in the file.
    """
    save_ai_config(provider="gemini", api_key=FAKE_KEY, model="gemini-2.5-flash")
    stored = _raw("gemini_api_key")
    assert stored and FAKE_KEY not in stored and secret_settings.is_sealed(stored), stored[:16]


def test_every_older_reader_unseals_it():
    """agno_agent and repurposer read the gemini copy directly."""
    import agno_agent
    import repurposer

    save_ai_config(provider="gemini", api_key=FAKE_KEY, model="gemini-2.5-flash")
    previous = {name: os.environ.pop(name, None) for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    try:
        assert repurposer.get_gemini_api_key() == FAKE_KEY
        engine = agno_agent.__dict__.get("agno_engine") or next(
            (value for value in agno_agent.__dict__.values()
             if hasattr(value, "get_gemini_api_key") and not isinstance(value, type)), None)
        if engine is None:
            engine = next(value for value in agno_agent.__dict__.values()
                          if isinstance(value, type) and hasattr(value, "get_gemini_api_key"))()
        assert engine.get_gemini_api_key() == FAKE_KEY
    finally:
        for name, value in previous.items():
            if value is not None:
                os.environ[name] = value


def test_a_key_stored_in_plain_text_by_an_older_version_still_works_and_is_then_sealed():
    _write_raw("ai_provider", "openai")
    _write_raw("ai_api_key", FAKE_KEY)
    assert get_current_ai_config().api_key == FAKE_KEY, "an upgrade made an existing key unreadable"

    conn = get_db()
    try:
        assert secret_settings.upgrade_plaintext(conn) >= 1
        assert secret_settings.upgrade_plaintext(conn) == 0, "sealing is not idempotent"
    finally:
        conn.close()
    assert secret_settings.is_sealed(_raw("ai_api_key"))
    assert get_current_ai_config().api_key == FAKE_KEY


def test_a_seal_this_machine_cannot_open_reads_as_no_key():
    """
    A database copied from another machine or Windows account carries a seal
    that cannot be opened here. It must read as "no key", never be handed to a
    provider as a string of ciphertext.
    """
    _write_raw("ai_provider", "openai")
    _write_raw("ai_api_key", "locenc2:" + "A" * 40)
    key = get_current_ai_config().api_key
    assert key == "", f"an unreadable seal came back as {key[:12]!r}"


def test_the_startup_path_seals_what_it_finds():
    """
    Run for real. The first version of this read the lifespan source for the
    name upgrade_plaintext, and passed with the call removed, because the
    import that names it was still there.
    """
    from fastapi.testclient import TestClient
    from app import app

    _write_raw("ai_provider", "openai")
    _write_raw("ai_api_key", FAKE_KEY)
    assert _raw("ai_api_key") == FAKE_KEY
    with TestClient(app):
        pass  # entering the client runs the startup path
    stored = _raw("ai_api_key")
    assert secret_settings.is_sealed(stored), "a key stored before this change is still readable after a start"
    assert get_current_ai_config().api_key == FAKE_KEY


def test_no_reader_takes_the_key_out_of_the_table_raw():
    """Every module that selects an AI key setting goes through unseal."""
    backend = os.path.join(REPO_ROOT, "studio", "backend")
    offenders = []
    for root, _, files in os.walk(backend):
        for name in files:
            if not name.endswith(".py") or name == "secret_settings.py":
                continue
            path = os.path.join(root, name)
            text = open(path, encoding="utf-8").read()
            reads = "key = 'gemini_api_key'" in text or 'rows.get("ai_api_key"' in text
            if reads and "_unseal_setting" not in text:
                offenders.append(os.path.relpath(path, REPO_ROOT))
    assert not offenders, f"these read an AI key setting without unsealing it: {offenders}"
