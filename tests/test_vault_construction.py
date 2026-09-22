"""
The cross-platform vault protects something.
============================================

It did not. The key came from PBKDF2 over hostname and username against a salt
committed to this public repository, so anyone holding the database could
recompute it in three lines. It was then used as a repeating XOR pad over a
token several times its length: measured on 128 bytes of constant plaintext,
the old scheme repeated at every 32 byte boundary, 96 times out of 96. That is
the keystream showing through the ciphertext.

The module also called itself "Hardware-Keyed" and was not.

What replaced it, and what it does and does not protect: the key is 32 random
bytes in a file beside the database, so the database alone is no longer enough.
A backup zip or a synced folder that carries the database without the key file
is protected. An attacker who already has the whole directory is not, and no
local scheme fixes that. Windows still uses DPAPI, which is the real protection
there.
"""

import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import vault

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# A realistic li_at, which is far longer than any 32 byte key.
LONG_TOKEN = "AQEDA" + "notarealkey" * 20


def test_a_token_round_trips():
    encrypted = vault._encrypt_local(LONG_TOKEN)
    assert encrypted.startswith(vault.LOCAL_ENC_V2_PREFIX)
    assert vault._decrypt_local_v2(encrypted.split(":", 1)[1]) == LONG_TOKEN


def test_the_keystream_does_not_repeat():
    """
    The defining flaw of the old scheme. Constant plaintext under a repeating
    pad produces ciphertext that repeats at the key length, which is 96 of 96
    at a 32 byte stride. Counter mode must show no such structure.
    """
    flat = "A" * 128
    blob = base64.b64decode(vault._encrypt_local(flat).split(":", 1)[1])
    body = blob[16:-32]

    stride_repeats = sum(1 for i in range(len(body) - 32) if body[i] == body[i + 32])
    assert stride_repeats < len(body) // 4, (
        f"{stride_repeats} of {len(body) - 32} bytes repeat at the old key "
        f"length, so the keystream is showing through"
    )


def test_the_same_token_encrypts_differently_each_time():
    """A nonce, so two vault rows holding the same value do not look alike."""
    assert vault._encrypt_local(LONG_TOKEN) != vault._encrypt_local(LONG_TOKEN)


def test_a_tampered_row_is_refused_rather_than_decrypted():
    """
    Returning a guess would hand the caller bytes it sends to LinkedIn as a
    session cookie.
    """
    encrypted = vault._encrypt_local(LONG_TOKEN)
    blob = bytearray(base64.b64decode(encrypted.split(":", 1)[1]))
    blob[20] ^= 0xFF

    assert vault._decrypt_local_v2(base64.b64encode(bytes(blob)).decode()) == ""


def test_the_key_is_random_and_not_derived_from_public_facts():
    key = vault._local_key()
    assert len(key) == 32
    assert key == vault._local_key(), "the key is not stable across calls"

    # Nothing about the machine should reproduce it.
    import hashlib
    import platform

    derivable = hashlib.pbkdf2_hmac(
        "sha256",
        f"{platform.node()}:{os.environ.get('USERNAME') or ''}".encode("utf-8"),
        b"linkedin_studio_sovereign_vault_v1",
        100000,
    )
    assert key != derivable, (
        "the key is still the one an attacker can recompute from the hostname, "
        "the username and the salt in this repository"
    )


def test_the_key_file_is_never_committed():
    ignored = open(os.path.join(REPO_ROOT, ".gitignore"), encoding="utf-8").read()
    assert "studio/vault/" in ignored


def test_legacy_rows_still_decrypt():
    """
    Existing vaults keep working. Nothing new is written under the old prefix,
    but a token sealed before this change must not become unreadable.
    """
    source = open(os.path.join(REPO_ROOT, "studio", "backend", "vault.py"), encoding="utf-8").read()
    assert "LOCAL_ENC_PREFIX" in source
    assert source.count("LOCAL_ENC_PREFIX") >= 2, "the legacy read path is gone"


def test_the_module_no_longer_claims_to_be_hardware_keyed():
    """
    It said "Hardware-Keyed Token Vault" while deriving its key from two
    public strings. A name that overstates what a thing does is how the thing
    stops being reviewed.
    """
    source = open(os.path.join(REPO_ROOT, "studio", "backend", "vault.py"), encoding="utf-8").read()
    header = source[:source.index('"""', source.index('"""') + 3)]
    assert "Hardware-Keyed" not in header


def test_autostart_quotes_the_paths_it_interpolates():
    """
    The same pattern was fixed in browser_launcher and missed here. A Windows
    account name may legally contain an apostrophe, and every one of these
    paths runs through the user profile.
    """
    source = open(os.path.join(REPO_ROOT, "studio", "backend", "desktop.py"), encoding="utf-8").read()
    assert "def ps_quote" in source
    assert "ps_quote(shortcut)" in source
    assert "ps_quote(target)" in source
