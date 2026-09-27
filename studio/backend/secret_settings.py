"""
Settings that are secrets, sealed at rest.

The LinkedIn session cookies have gone through the vault since it existed. The
AI provider key never did: save_ai_config wrote it into the settings table as
typed, and four readers took it back out the same way. The README called that
table an "encrypted vault", and the help article on what leaves this machine
had to say plainly that it was not.

So the key goes through the same seal as li_at: Windows DPAPI where it is
available, the vault's local key elsewhere. The consequence is the same one
the cookies already carry, and it is the point rather than a side effect: a
database copied to another machine or another Windows account does not carry a
usable key with it. decrypt_token returns an empty string for a seal it cannot
open, so such a key reads as "no key configured" rather than being sent to a
provider as garbage.

One list decides which settings are secret. Readers call unseal and writers
call seal, so a new secret is one line here rather than a hunt through every
module that touches the table.
"""

from typing import Any, Optional

try:
    from .vault import DPAPI_PREFIX, LOCAL_ENC_PREFIX, LOCAL_ENC_V2_PREFIX, decrypt_token, encrypt_token
except ImportError:
    from vault import DPAPI_PREFIX, LOCAL_ENC_PREFIX, LOCAL_ENC_V2_PREFIX, decrypt_token, encrypt_token

SECRET_SETTING_KEYS = frozenset({"ai_api_key", "gemini_api_key"})

_SEALED_PREFIXES = (DPAPI_PREFIX, LOCAL_ENC_V2_PREFIX, LOCAL_ENC_PREFIX)


def is_sealed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_SEALED_PREFIXES)


def seal(key: str, value: Any) -> str:
    """The value to store for a setting: sealed if the setting is a secret."""
    text = "" if value is None else str(value)
    if key not in SECRET_SETTING_KEYS or not text or is_sealed(text):
        return text
    return encrypt_token(text)


def unseal(key: str, value: Any) -> str:
    """
    The usable value of a stored setting.

    A secret stored in plain text by an older version still reads correctly,
    because decrypt_token hands back anything without a seal prefix unchanged.
    upgrade_plaintext is what then seals it.
    """
    text = "" if value is None else str(value)
    if key not in SECRET_SETTING_KEYS:
        return text
    return decrypt_token(text)


def upgrade_plaintext(conn) -> int:
    """
    Seals any secret still stored in plain text. Returns how many it sealed.

    Run at startup. Idempotent: a sealed value is left alone, so the second
    run seals nothing. Without this, a key saved before the change would stay
    readable in the file until the next time someone happened to save it.
    """
    sealed = 0
    for key in SECRET_SETTING_KEYS:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        value: Optional[str] = row[0] if row else None
        if not value or is_sealed(value):
            continue
        conn.execute(
            "UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (encrypt_token(value), key),
        )
        sealed += 1
    if sealed:
        conn.commit()
    return sealed
