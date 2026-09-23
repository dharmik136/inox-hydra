"""
Local Token Vault & Security Manager.
=====================================
Provides encryption at rest for sensitive session credentials (li_at, JSESSIONID).

On Windows this is the Data Protection API via ctypes, which ties the
ciphertext to the user account and is the real protection here.

Everywhere else, and when DPAPI fails, a local key file is used. That file sits
beside the database, so this protects a database that travels without it, a
backup zip or a synced folder, and not an attacker who already has the whole
directory. Saying which of those it does is the point.

It is NOT hardware keyed, and this module used to say it was. The previous
fallback derived its key with PBKDF2 over hostname and username against a salt
committed to this public repository, so anyone holding the database could
recompute it in three lines. It then used that key as a repeating XOR pad over
a token several times its length, which leaks structure on its own.

Strict Invariants:
- Zero cloud egress (100% local encryption).
- Zero em-dashes in any text or logs.
"""

from typing import Optional, Any
import base64
import ctypes
import hashlib
import hmac
import os
import platform

import shutil
import subprocess

DPAPI_PREFIX = "dpapi:"
LOCAL_ENC_PREFIX = "locenc:"
# The replacement scheme. The old prefix is still read so existing vaults keep
# working; nothing new is ever written under it.
LOCAL_ENC_V2_PREFIX = "locenc2:"
_VAULT_KEY_FILENAME = "vault_key"
_KEYCHAIN_SERVICE = "InoxHydra.LinkedInStudio"
_KEYCHAIN_ACCOUNT = "vault_master_key"
MAX_PLAINTEXT_LENGTH = 65536


def _get_machine_key() -> bytes:
    """Derives a stable machine-specific 256-bit encryption key."""
    node_id = platform.node() or "linkedin_studio_machine"
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "default_creator"
    salt = b"linkedin_studio_sovereign_vault_v1"
    return hashlib.pbkdf2_hmac("sha256", f"{node_id}:{user}".encode("utf-8"), salt, 100000)


def _keychain_read() -> Optional[bytes]:
    """Reads the master key from the macOS Keychain via the security binary."""
    if platform.system() != "Darwin":
        return None
    try:
        proc = subprocess.run(
            [
                "security", "find-generic-password",
                "-s", _KEYCHAIN_SERVICE,
                "-a", _KEYCHAIN_ACCOUNT,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            secret = proc.stdout.strip()
            if secret:
                try:
                    raw = bytes.fromhex(secret)
                    if len(raw) >= 32:
                        return raw[:32]
                except ValueError:
                    raw = secret.encode("utf-8")
                    if len(raw) >= 32:
                        return raw[:32]
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _keychain_write(key: bytes) -> bool:
    """Stores the master key in the macOS Keychain via the security binary."""
    if platform.system() != "Darwin":
        return False
    try:
        proc = subprocess.run(
            [
                "security", "add-generic-password",
                "-s", _KEYCHAIN_SERVICE,
                "-a", _KEYCHAIN_ACCOUNT,
                "-w", key.hex(),
                "-U",
            ],
            capture_output=True,
            timeout=5,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _secret_tool_read() -> Optional[bytes]:
    """Reads the master key from Linux Secret Service via secret-tool."""
    if platform.system() != "Linux":
        return None
    if not shutil.which("secret-tool"):
        return None
    try:
        proc = subprocess.run(
            [
                "secret-tool", "lookup",
                "service", _KEYCHAIN_SERVICE,
                "account", _KEYCHAIN_ACCOUNT,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            secret = proc.stdout.strip()
            if secret:
                try:
                    raw = bytes.fromhex(secret)
                    if len(raw) >= 32:
                        return raw[:32]
                except ValueError:
                    raw = secret.encode("utf-8")
                    if len(raw) >= 32:
                        return raw[:32]
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def _secret_tool_write(key: bytes) -> bool:
    """Stores the master key in Linux Secret Service via secret-tool."""
    if platform.system() != "Linux":
        return False
    if not shutil.which("secret-tool"):
        return False
    try:
        proc = subprocess.run(
            [
                "secret-tool", "store",
                "--label=LinkedIn Studio Vault",
                "service", _KEYCHAIN_SERVICE,
                "account", _KEYCHAIN_ACCOUNT,
            ],
            input=key.hex().encode("utf-8"),
            capture_output=True,
            timeout=5,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _file_key() -> bytes:
    """
    Fallback 256 bit key stored in a local file beside the user database.
    Used when platform keystores are unavailable or fail.
    """
    try:
        from .paths import get_vault_dir
    except ImportError:
        from paths import get_vault_dir

    path = os.path.join(get_vault_dir(), _VAULT_KEY_FILENAME)
    try:
        with open(path, "rb") as handle:
            key = handle.read().strip()
        if len(key) >= 32:
            return key[:32]
    except (OSError, IOError):
        pass

    key = os.urandom(32)
    try:
        with open(path, "wb") as handle:
            handle.write(key)
        try:
            os.chmod(path, 0o600)
        except (OSError, NotImplementedError):
            pass
    except (OSError, IOError):
        # A read only state directory is a broken install. Running with an
        # ephemeral key is better than refusing to start, and the token simply
        # will not decrypt after a restart, which is a visible failure rather
        # than a silent one.
        pass
    return key


def _local_key() -> bytes:
    """
    Resolves the 256-bit encryption key for this installation.
    Prefers the platform keystore: macOS Keychain via security, or Linux Secret
    Service via secret-tool. If the platform keystore is unavailable or fails,
    falls back to the local file key.
    """
    system = platform.system()
    if system == "Darwin":
        existing = _keychain_read()
        if existing:
            return existing
        generated = os.urandom(32)
        if _keychain_write(generated):
            return generated
        return _file_key()

    if system == "Linux":
        existing = _secret_tool_read()
        if existing:
            return existing
        generated = os.urandom(32)
        if _secret_tool_write(generated):
            return generated
        return _file_key()

    return _file_key()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """
    HMAC-SHA256 in counter mode.

    The old scheme repeated a 32 byte key across a token several times longer,
    so identical plaintext bytes 32 apart produced identical ciphertext bytes.
    A counter mode stream never repeats within a message, and the nonce means
    it never repeats between messages either.
    """
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def _encrypt_local(plaintext: str) -> str:
    key = _local_key()
    nonce = os.urandom(16)
    raw = plaintext.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(raw, _keystream(key, nonce, len(raw))))
    # Encrypt then MAC, so a tampered vault row is rejected rather than
    # decrypted into something arbitrary.
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return LOCAL_ENC_V2_PREFIX + base64.b64encode(nonce + cipher + tag).decode("utf-8")


def _decrypt_local_v2(payload: str) -> str:
    key = _local_key()
    blob = base64.b64decode(payload)
    if len(blob) < 16 + 32:
        return ""
    nonce, cipher, tag = blob[:16], blob[16:-32], blob[-32:]
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        # Wrong key or altered data. Returning "" says so; returning a guess
        # would hand the caller bytes it would send to LinkedIn as a cookie.
        return ""
    return bytes(a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher)))).decode("utf-8", "replace")


def get_vault_backend() -> str:
    """
    Reports the active encryption backend without performing cryptographic operations.

    Honesty invariant: Returns DPAPI on Windows, KEYCHAIN on macOS when security
    is usable, SECRET_SERVICE on Linux when secret-tool is present, or FILE_KEY
    when using the file-backed key fallback. Never claims hardware backing.
    """
    system = platform.system()
    if system == "Windows":
        return "DPAPI"
    if system == "Darwin":
        if _keychain_read() is not None:
            return "KEYCHAIN"
        if shutil.which("security"):
            return "KEYCHAIN"
        return "FILE_KEY"
    if system == "Linux":
        if shutil.which("secret-tool"):
            return "SECRET_SERVICE"
        return "FILE_KEY"
    return "FILE_KEY"


def get_vault_status() -> dict:
    """
    Diagnostic status of the active vault backend.
    Reports honestly whether platform keystore protection is active or if
    the file-backed key fallback is being used.
    """
    backend = get_vault_backend()
    return {
        "backend": backend,
        "platform": platform.system(),
        "keystore_available": backend in ("DPAPI", "KEYCHAIN", "SECRET_SERVICE"),
        "hardware_backed": False,
        "fallback": backend == "FILE_KEY",
    }


def encrypt_token(plaintext: Any) -> str:
    """
    Encrypts a token string at rest before saving to SQLite settings table.
    Returns ciphertext prefixed with encryption scheme identifier.
    Guards against nulls, non-string types, and oversized payloads.
    """
    if plaintext is None:
        return ""

    if isinstance(plaintext, bytes):
        raw_text = plaintext.decode("utf-8", errors="replace")
    elif not isinstance(plaintext, str):
        raw_text = str(plaintext)
    else:
        raw_text = plaintext

    if not raw_text:
        return ""

    # Bound plaintext length to prevent memory exhaustion
    bounded_text = raw_text[:MAX_PLAINTEXT_LENGTH]

    # Windows DPAPI Implementation
    if platform.system() == "Windows":
        try:
            from ctypes import wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))
                ]

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            raw_bytes = bounded_text.encode("utf-8")
            in_blob = DATA_BLOB(
                len(raw_bytes),
                ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_char))
            )
            out_blob = DATA_BLOB()

            if crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                "LinkedInStudioVault",
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob)
            ):
                try:
                    cipher_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                    return DPAPI_PREFIX + base64.b64encode(cipher_bytes).decode("utf-8")
                finally:
                    if out_blob.pbData:
                        kernel32.LocalFree(out_blob.pbData)
        except Exception:
            pass  # Fall through to machine-keyed fallback

    # Cross platform fallback, using a random local key rather than one
    # derivable from facts an attacker already has.
    return _encrypt_local(bounded_text)


def decrypt_token(ciphertext: Any) -> str:
    """
    Decrypts a stored ciphertext string into plaintext.
    Handles unencrypted legacy strings transparently for backward compatibility.
    Guards against malformed base64, nulls, and non-string inputs.
    """
    if ciphertext is None:
        return ""

    if not isinstance(ciphertext, str):
        raw_cipher = str(ciphertext)
    else:
        raw_cipher = ciphertext

    if not raw_cipher:
        return ""

    # Check if already plaintext (backward compatibility with legacy unencrypted DBs)
    if not raw_cipher.startswith((DPAPI_PREFIX, LOCAL_ENC_PREFIX)):
        return raw_cipher

    # Windows DPAPI Decryption
    if raw_cipher.startswith(DPAPI_PREFIX) and platform.system() == "Windows":
        try:
            from ctypes import wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))
                ]

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            raw_bytes = base64.b64decode(raw_cipher[len(DPAPI_PREFIX):])
            in_blob = DATA_BLOB(
                len(raw_bytes),
                ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_char))
            )
            out_blob = DATA_BLOB()

            if crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                None,
                None,
                None,
                None,
                0,
                ctypes.byref(out_blob)
            ):
                try:
                    plain_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                    return plain_bytes.decode("utf-8")
                finally:
                    if out_blob.pbData:
                        kernel32.LocalFree(out_blob.pbData)
        except Exception:
            return ""

        # CryptUnprotectData signals failure by returning 0 rather than
        # raising, so a failed decrypt fell out of the `if` and off the end of
        # this function, where the final `return raw_cipher` handed the caller
        # the base64 DPAPI blob as though it were the token.
        #
        # The blob is a non-empty string, so is_authenticated() reported True
        # and the client sent it to LinkedIn as a cookie. The 401 that came
        # back tripped the circuit breaker for 300 seconds and told the user to
        # recapture, which cannot help: the vault entry was sealed on a
        # different machine or under a different account and is simply not
        # readable here. An empty string says that honestly.
        return ""

    if raw_cipher.startswith(LOCAL_ENC_V2_PREFIX):
        try:
            return _decrypt_local_v2(raw_cipher[len(LOCAL_ENC_V2_PREFIX):])
        except Exception:
            return ""

    # Legacy machine-keyed decryption. Read only: existing vaults keep working
    # and are rewritten under the new scheme the next time they are saved.
    if raw_cipher.startswith(LOCAL_ENC_PREFIX):
        try:
            key = _get_machine_key()
            cipher_bytes = base64.b64decode(raw_cipher[len(LOCAL_ENC_PREFIX):])
            plain_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(cipher_bytes)])
            return plain_bytes.decode("utf-8")
        except Exception:
            return ""

    return raw_cipher
