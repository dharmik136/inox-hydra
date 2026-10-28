"""
The Telegram bot: what it says back, and how it reaches Telegram.
=================================================================

ingress.py asks Telegram for the messages the creator sends their own bot
and saves them. This module is the bot's side of the conversation (2.11.0).

Every request goes to the Bot API at API_BASE, through egress.py under the
category the ingress already uses, so the Local security tab counts it and
INOX_NO_EGRESS refuses it. The suite points API_BASE at a fake Bot API on
loopback (tests/telegram_fake.py); nothing in the suite reaches Telegram.

Strict Invariants:
- Zero em-dashes.
- Nothing about another member is ever sent: no name, no comment text.
"""

# The Bot API. One base for every method, so the suite can stand in for it.
API_BASE = "https://api.telegram.org"


def method_url(token: str, method: str) -> str:
    """The address of one Bot API method for this bot. It carries the token: never logged or shown."""
    return f"{API_BASE}/bot{token}/{method}"
