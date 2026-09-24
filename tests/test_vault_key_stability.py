"""
Vault Key Stability
===================
A transient keystore failure must never cost the creator their session.

_local_key resolved the encryption key on every single call, and on Linux it
treated "the keystore read failed" the same as "the keystore holds no key":
both generated a fresh random key and stored it, overwriting whatever was
already there. secret-tool lookup fails for ordinary reasons, a locked keyring,
a D-Bus session that is not up yet, a five second timeout under load, and any
one of them silently rotated the key.

Two consequences, both observed:

1. Inside a single process, encrypt and decrypt could resolve different keys,
   so a round trip broke with no failure anywhere. This is what made the vault
   tests flaky on Linux CI while passing on Windows and macOS.

2. Across runs the damage was permanent. The real key had been overwritten, so
   every token ever encrypted under it stopped opening, and the creator's
   LinkedIn session was gone with nothing reported.

The repair is three things: resolve once per process, never write over a
keystore that is merely unavailable, and verify a candidate key against the
message tag rather than assuming the current one. The tag already existed, so
trying more than one key is safe: a wrong key is detected, never guessed at.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from studio.backend import vault  # noqa: E402


@pytest.fixture
def linux_keystore(monkeypatch):
    """
    A simulated Linux install with a working secret-tool, whose reads can be
    made to fail on demand. The real Linux path cannot be exercised from
    Windows or macOS CI, and this is the branch that carries the defect.
    """
    store = {}
    state = {"fail_reads": False, "writes": 0}

    monkeypatch.setattr(vault.platform, "system", lambda: "Linux")
    monkeypatch.setattr(vault.shutil, "which", lambda name: "/usr/bin/secret-tool")

    def read():
        return None if state["fail_reads"] else store.get("key")

    def absent():
        # A failing read is not an absent secret. The real implementation asks
        # secret-tool; here the distinction is explicit.
        return not state["fail_reads"] and "key" not in store

    def write(key):
        state["writes"] += 1
        store["key"] = key
        return True

    monkeypatch.setattr(vault, "_secret_tool_read", read)
    monkeypatch.setattr(vault, "_secret_tool_is_absent", absent)
    monkeypatch.setattr(vault, "_secret_tool_write", write)

    # The file key lives beside the database, so point that somewhere throwaway.
    monkeypatch.setattr(vault, "_file_key_if_present", lambda: None)
    monkeypatch.setattr(vault, "_file_key", lambda: b"F" * 32)

    vault.reset_key_cache()
    yield state, store
    vault.reset_key_cache()


# Deliberately not shaped like a real li_at cookie. A literal starting
# AQEDAT is what a genuine LinkedIn session token looks like, and
# test_distribution_hygiene refuses to let one sit in a tracked file even
# as a fixture. It caught this one.
TOKEN = "vault-round-trip-fixture-value-0123456789"


def test_a_failed_keystore_read_does_not_replace_the_key(linux_keystore):
    """
    The heart of it. One failed lookup used to mint a new key and store it,
    which destroyed every existing ciphertext.
    """
    state, store = linux_keystore

    cipher = vault.encrypt_token(TOKEN)
    original = store["key"]
    assert vault.decrypt_token(cipher) == TOKEN

    # A hiccup, then a fresh process resolving the key again.
    state["fail_reads"] = True
    vault.reset_key_cache()
    vault.decrypt_token(cipher)

    assert store["key"] == original, (
        "the stored key was replaced because a read failed, which makes every "
        "token encrypted under it permanently undecryptable"
    )


def test_the_token_survives_a_transient_failure(linux_keystore):
    """
    Recoverable, not merely non-destructive: once the keystore answers again
    the same ciphertext opens.
    """
    state, _ = linux_keystore

    cipher = vault.encrypt_token(TOKEN)

    state["fail_reads"] = True
    vault.reset_key_cache()
    during = vault.decrypt_token(cipher)

    state["fail_reads"] = False
    vault.reset_key_cache()
    after = vault.decrypt_token(cipher)

    assert after == TOKEN, "the session did not come back when the keystore did"
    # During the outage the honest answer is nothing, never a guess: the caller
    # would send whatever it got to LinkedIn as a cookie.
    assert during in ("", TOKEN)


def test_the_key_is_resolved_once_per_process(linux_keystore):
    """
    Encrypt and decrypt resolved independently, so a failure between them broke
    a round trip inside one run with nothing raising. That is the flake.
    """
    state, _ = linux_keystore

    cipher = vault.encrypt_token(TOKEN)
    state["fail_reads"] = True  # no reset: the process already knows its key

    assert vault.decrypt_token(cipher) == TOKEN, (
        "a keystore read failed between encrypt and decrypt and the round trip "
        "broke inside a single process"
    )


def test_a_key_written_while_the_keystore_was_down_still_opens(linux_keystore):
    """
    An install can end up holding two keys: the keystore key, and a file key
    written during an outage. Tokens from the outage must not stop opening the
    moment the keystore returns.
    """
    state, _ = linux_keystore

    # Encrypted while the keystore was unavailable, so under the file key.
    state["fail_reads"] = True
    vault.reset_key_cache()
    cipher = vault.encrypt_token(TOKEN)

    # The keystore comes back and becomes the primary again.
    state["fail_reads"] = False
    monkey_file_key = b"F" * 32
    vault.reset_key_cache()
    vault._file_key_if_present = lambda: monkey_file_key

    assert vault.decrypt_token(cipher) == TOKEN, (
        "a token written during a keystore outage stopped opening once the "
        "keystore recovered"
    )


def test_a_genuinely_empty_keystore_is_still_initialised(linux_keystore):
    """
    The guard must not prevent a first run from creating a key. Absent is a
    real state and is the one case where writing is correct.
    """
    state, store = linux_keystore
    assert "key" not in store

    cipher = vault.encrypt_token(TOKEN)
    assert store.get("key"), "a fresh install never stored a key"
    assert vault.decrypt_token(cipher) == TOKEN
    assert state["writes"] == 1, f"the key was written {state['writes']} times on one install"


def test_a_wrong_key_still_yields_nothing_rather_than_a_guess(linux_keystore):
    """
    Trying several candidates must not weaken the check the tag exists for.
    """
    _, store = linux_keystore

    cipher = vault.encrypt_token(TOKEN)
    store["key"] = b"X" * 32
    vault.reset_key_cache()
    vault._file_key_if_present = lambda: b"Y" * 32

    assert vault.decrypt_token(cipher) == "", (
        "decryption under an unrelated key returned something, which the caller "
        "would send to LinkedIn as a session cookie"
    )
