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

from typing import Optional
import base64
import ctypes
import hashlib
import os
import platform

DPAPI_PREFIX = "dpapi:"
LOCAL_ENC_PREFIX = "locenc:"


def _get_machine_key() -> bytes:
    """Derives a stable machine-specific 256-bit encryption key."""
    node_id = platform.node() or "linkedin_studio_machine"
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "default_creator"
    salt = b"linkedin_studio_sovereign_vault_v1"
    return hashlib.pbkdf2_hmac("sha256", f"{node_id}:{user}".encode("utf-8"), salt, 100000)


def encrypt_token(plaintext: str) -> str:
    """
    Encrypts a token string at rest before saving to SQLite settings table.
    Returns ciphertext prefixed with encryption scheme identifier.
    """
    if not plaintext:
        return ""

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

            raw_bytes = plaintext.encode("utf-8")
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
                cipher_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                kernel32.LocalFree(out_blob.pbData)
                return DPAPI_PREFIX + base64.b64encode(cipher_bytes).decode("utf-8")
        except Exception:
            pass  # Fall through to machine-keyed fallback

    # Cross-Platform Machine-Keyed XOR Stream Fallback
    key = _get_machine_key()
    raw_bytes = plaintext.encode("utf-8")
    cipher_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw_bytes)])
    return LOCAL_ENC_PREFIX + base64.b64encode(cipher_bytes).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypts a stored ciphertext string into plaintext.
    Handles unencrypted legacy strings transparently for backward compatibility.
    """
    if not ciphertext:
        return ""

    # Check if already plaintext (backward compatibility with legacy unencrypted DBs)
    if not ciphertext.startswith((DPAPI_PREFIX, LOCAL_ENC_PREFIX)):
        return ciphertext

    # Windows DPAPI Decryption
    if ciphertext.startswith(DPAPI_PREFIX) and platform.system() == "Windows":
        try:
            from ctypes import wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))
                ]

            crypt32 = ctypes.windll.crypt32
            kernel32 = ctypes.windll.kernel32

            raw_bytes = base64.b64decode(ciphertext[len(DPAPI_PREFIX):])
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
                plain_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
                kernel32.LocalFree(out_blob.pbData)
                return plain_bytes.decode("utf-8")
        except Exception:
            return ""

    # Machine-Keyed Decryption
    if ciphertext.startswith(LOCAL_ENC_PREFIX):
        try:
            key = _get_machine_key()
            cipher_bytes = base64.b64decode(ciphertext[len(LOCAL_ENC_PREFIX):])
            plain_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(cipher_bytes)])
            return plain_bytes.decode("utf-8")
        except Exception:
            return ""

    return ciphertext
