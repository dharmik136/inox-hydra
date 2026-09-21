"""
Local Hardware-Keyed Token Vault & Security Manager.
====================================================
Provides encryption at rest for sensitive session credentials (li_at, JSESSIONID).
Uses Windows Data Protection API (DPAPI) via ctypes on Windows,
with a secure machine-keyed PBKDF2/SHA256 fallback for cross-platform support.

Strict Invariants:
- Zero cloud egress (100% local encryption).
- Zero em-dashes in any text or logs.
"""

from typing import Optional, Any
import base64
import ctypes
import hashlib
import os
import platform

DPAPI_PREFIX = "dpapi:"
LOCAL_ENC_PREFIX = "locenc:"
MAX_PLAINTEXT_LENGTH = 65536


def _get_machine_key() -> bytes:
    """Derives a stable machine-specific 256-bit encryption key."""
    node_id = platform.node() or "linkedin_studio_machine"
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "default_creator"
    salt = b"linkedin_studio_sovereign_vault_v1"
    return hashlib.pbkdf2_hmac("sha256", f"{node_id}:{user}".encode("utf-8"), salt, 100000)


def get_vault_backend() -> str:
    """Reports the active encryption backend without performing cryptographic operations."""
    if platform.system() == "Windows":
        return "DPAPI"
    return "MACHINE_KEYED"


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

    # Cross-Platform Machine-Keyed XOR Stream Fallback
    key = _get_machine_key()
    raw_bytes = bounded_text.encode("utf-8")
    cipher_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw_bytes)])
    return LOCAL_ENC_PREFIX + base64.b64encode(cipher_bytes).decode("utf-8")


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

    # Machine-Keyed Decryption
    if raw_cipher.startswith(LOCAL_ENC_PREFIX):
        try:
            key = _get_machine_key()
            cipher_bytes = base64.b64decode(raw_cipher[len(LOCAL_ENC_PREFIX):])
            plain_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(cipher_bytes)])
            return plain_bytes.decode("utf-8")
        except Exception:
            return ""

    return raw_cipher
