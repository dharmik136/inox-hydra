"""
The offline licence: a signature the studio checks itself.
==========================================================

ed25519.py is the RFC 8032 reference algorithm, checked here against the RFC's
own test vectors (section 7.1) and, where node is installed, against Node's
built-in Ed25519. Tests that only sign and verify with the same code would
pass whatever that code did, so the vectors are what hold it to the standard.

licensing.py is held to its promise that a key is refused or accepted, never
crashes the studio: a signed key with a bad field, a key built to exhaust the
parser, an unreadable file and a key that has already ended are all reported,
and none of them can replace a licence that works.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))

import ed25519  # noqa: E402
import licensing  # noqa: E402

# RFC 8032, section 7.1: TEST 1, TEST 2 and TEST 3.
RFC_VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]

TEST_SECRET = bytes(range(32))


@pytest.mark.parametrize("secret, public, message, signature", RFC_VECTORS)
def test_the_rfc_vectors(secret, public, message, signature):
    secret, public, message, signature = map(bytes.fromhex, (secret, public, message, signature))
    assert ed25519.public_key(secret) == public
    assert ed25519.sign(secret, message) == signature
    assert ed25519.verify(public, message, signature)


@pytest.mark.parametrize("secret, public, message, signature", RFC_VECTORS)
def test_a_changed_message_or_signature_fails(secret, public, message, signature):
    public, message, signature = map(bytes.fromhex, (public, message, signature))
    assert not ed25519.verify(public, message + b"\x00", signature)
    flipped = bytearray(signature)
    flipped[10] ^= 1
    assert not ed25519.verify(public, message, bytes(flipped))
    # S at or above the group order is refused, not reduced.
    s = int.from_bytes(signature[32:], "little") + 2 ** 252 + 27742317777372353535851937790883648493
    if s < 2 ** 256:
        assert not ed25519.verify(public, message, signature[:32] + s.to_bytes(32, "little"))


def test_verify_answers_false_on_garbage():
    for public, signature in ((b"", b""), (b"\xff" * 32, b"\xff" * 64), (b"x" * 31, b"y" * 64), ("text", "text")):
        assert ed25519.verify(public, b"m", signature) is False


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_it_agrees_with_node():
    script = (
        "const c=require('crypto');const [sk,msg]=process.argv.slice(-2);"
        "const der=Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),Buffer.from(sk,'hex')]);"
        "const key=c.createPrivateKey({key:der,format:'der',type:'pkcs8'});"
        "process.stdout.write(c.sign(null,Buffer.from(msg,'hex'),key).toString('hex'));"
    )
    for n in range(5):
        secret, message = os.urandom(32), os.urandom(n * 17)
        theirs = subprocess.run(["node", "-e", script, secret.hex(), message.hex()],
                                capture_output=True, text=True, check=True).stdout
        assert ed25519.sign(secret, message).hex() == theirs


# ---------------------------------------------------------------------------
# The licence
# ---------------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(TEST_SECRET)).decode()])
    return tmp_path


def _signed(**fields):
    payload = {"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
               "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"}
    payload.update(fields)
    return licensing.encode(payload, lambda message: ed25519.sign(TEST_SECRET, message))


def _raw(body: str) -> str:
    """A licence whose payload is exactly `body`, signed."""
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    signature = ed25519.sign(TEST_SECRET, f"IHL1.{encoded}".encode())
    return f"IHL1.{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


@pytest.mark.parametrize("fields", [
    {"profiles": "five"}, {"profiles": 0}, {"profiles": 10 ** 6}, {"profiles": True}, {"profiles": 2.5},
    {"kind": "monthlyish"}, {"tier": "enterprise"}, {"expires_at": "soon"}, {"expires_at": None},
    {"expires_at": 20990101},
])
def test_a_signed_key_with_a_bad_field_is_refused_and_changes_nothing(vault, fields):
    assert licensing.install(_signed())["status"] == "success"
    result = licensing.install(_signed(**fields))
    assert result["status"] == "error"
    state = licensing.current()
    assert state["status"] == "active" and state["profile_limit"] == 5, "a refused key replaced a working one"


def test_a_key_built_to_exhaust_the_parser_is_refused(vault):
    deep = "[" * 3000 + "]" * 3000
    assert licensing.read_licence_text(_raw(deep))["valid"] is False
    assert licensing.read_licence_text("IHL1." + "A" * 5000 + ".B")["valid"] is False


def test_an_unsigned_payload_is_never_parsed(vault, monkeypatch):
    called = []
    monkeypatch.setattr(licensing.json, "loads", lambda *a, **k: called.append(1))
    encoded = base64.urlsafe_b64encode(b'{"tier": "agency"}').decode().rstrip("=")
    assert licensing.read_licence_text(f"IHL1.{encoded}.AAAA")["valid"] is False
    assert called == [], "the payload was parsed before its signature was checked"


def test_an_ended_key_cannot_replace_a_working_one(vault):
    licensing.install(_signed())
    result = licensing.install(_signed(tier="creator", profiles=1, expires_at="2020-01-01"))
    assert result["status"] == "error" and "2020-01-01" in result["message"]
    assert licensing.current()["tier"] == "agency"


def test_a_licence_ends_into_the_free_tier(vault):
    licensing.install(_signed(expires_at="2026-12-31"))
    assert licensing.current(today=date(2026, 12, 31))["status"] == "active"
    later = licensing.current(today=date(2027, 1, 1))
    assert later["status"] == "expired" and later["tier"] == "free" and later["profile_limit"] == 1


def test_a_lifetime_licence_does_not_end(vault):
    licensing.install(_signed(tier="creator", kind="lifetime", profiles=1, expires_at=None))
    assert licensing.current(today=date(2040, 1, 1))["status"] == "active"


def test_an_unreadable_licence_file_is_reported(vault):
    licensing.install(_signed())
    with open(os.path.join(str(vault), "vault", licensing.LICENCE_FILENAME), "wb") as handle:
        handle.write("é".encode("utf-8"))
    state = licensing.current()
    assert state["status"] == "invalid" and state["reason"]
    assert state["tier"] == "free"


def test_a_damaged_stored_key_never_breaks_the_studio(vault):
    os.makedirs(os.path.join(str(vault), "vault"), exist_ok=True)
    with open(os.path.join(str(vault), "vault", licensing.LICENCE_FILENAME), "w") as handle:
        handle.write(_raw(json.dumps({"tier": "agency", "kind": "annual", "profiles": [1]})))
    state = licensing.current()
    assert state["status"] == "invalid" and state["profile_limit"] == 1


# ---------------------------------------------------------------------------
# The vendor's tool
# ---------------------------------------------------------------------------

def test_the_tool_issues_only_what_the_price_list_sells():
    import licence_keys

    good = licence_keys.build_payload("buyer@example.com", "agency", "monthly", today=date(2026, 10, 19))
    assert good["profiles"] == 5 and good["expires_at"] == "2026-11-19"
    lifetime = licence_keys.build_payload("buyer@example.com", "creator", "lifetime", today=date(2026, 10, 19))
    assert lifetime["expires_at"] is None and lifetime["updates_until"] == "2027-10-19"
    for args in (("agency", "lifetime", 0, 0), ("creator", "monthly", 0, 0), ("agency", "annual", 6, 0),
                 ("creator", "annual", 2, 0), ("agency", "annual", 0, -10), ("agency", "Annual", 0, 0)):
        tier, kind, profiles, days = args
        with pytest.raises(ValueError):
            licence_keys.build_payload("buyer@example.com", tier, kind, profiles, days)


def test_the_tool_will_not_write_a_key_inside_the_repository(tmp_path):
    import licence_keys

    assert licence_keys._inside_repo(os.path.join(licence_keys.REPO, "keys"))
    assert not licence_keys._inside_repo(str(tmp_path))
    assert licence_keys.new_keypair(os.path.join(licence_keys.REPO, "keys")) == 2
    assert not os.path.exists(os.path.join(licence_keys.REPO, "keys"))


def test_a_signing_key_is_ignored_by_git():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = subprocess.run(["git", "check-ignore", "-q", "somewhere/ed25519.secret"], cwd=root)
    assert result.returncode == 0, "a signing key could be committed"
